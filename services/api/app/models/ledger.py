from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ledger(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "ref_order_id", name="uq_ledger_user_type_order"),
        # The payment order is the durable idempotency key for a recharge.
        # SQLite/PostgreSQL both permit multiple NULLs in this constraint.
        UniqueConstraint("ref_payment_order_id", name="uq_ledger_payment_credit"),
        UniqueConstraint("ref_order_renewal_id", name="uq_ledger_order_renewal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int | None] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(32))  # recharge/withdraw/pay/revenue/refund
    direction: Mapped[str] = mapped_column(String(8))  # in/out
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    ref_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_payment_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_order_renewal_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_renewals.id"), nullable=True,
    )
    # Durable idempotency key for non-payment money events such as withdrawal
    # freeze, unfreeze, and manual payout completion.
    event_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
