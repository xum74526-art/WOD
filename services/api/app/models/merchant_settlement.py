from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MerchantSettlement(Base):
    """Immutable commercial settlement created from one confirmed sale event."""

    __tablename__ = "merchant_settlements"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_merchant_settlement_event"),
        UniqueConstraint("source_type", "source_id", name="uq_merchant_settlement_source"),
        UniqueConstraint("ledger_id", name="uq_merchant_settlement_ledger"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(128))
    policy_version: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(16))  # order / renewal
    source_id: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    order_renewal_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_renewals.id"), nullable=True, index=True,
    )
    buyer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    service_fee_bps: Mapped[int] = mapped_column(Integer)
    service_fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    policy_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="settled")
    ledger_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
