from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderFundingAllocation(Base):
    """Immutable source split for one order or renewal wallet debit.

    Merchant settlement still receives the full gross amount. The promotional
    portion is an explicit platform subsidy, while only ``cash_amount`` is
    eligible as an invitation commission base.
    """

    __tablename__ = "order_funding_allocations"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_order_funding_source"),
        UniqueConstraint("order_renewal_id", name="uq_order_funding_renewal"),
        CheckConstraint(
            "gross_amount = cash_amount + promotional_amount",
            name="ck_order_funding_conservation",
        ),
        CheckConstraint(
            "gross_amount >= 0 AND cash_amount >= 0 AND promotional_amount >= 0",
            name="ck_order_funding_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    order_renewal_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_renewals.id"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    promotional_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    policy_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True)
    policy_snapshot: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
