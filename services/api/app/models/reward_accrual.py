from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RewardAccrual(Base):
    """Versioned reward entitlement created from one auditable business event."""

    __tablename__ = "reward_accruals"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_reward_accrual_idempotency"),
        # A business event may earn at most one entitlement per program.  The
        # policy version is intentionally absent: replaying an old event after
        # a policy upgrade must return the original immutable snapshot instead
        # of creating a second reward.
        UniqueConstraint(
            "program_code",
            "source_type",
            "source_id",
            name="uq_reward_accrual_source",
        ),
        Index("ix_reward_accrual_due", "program_code", "status", "due_at"),
        Index("ix_reward_accrual_period", "program_code", "beneficiary_user_id", "period_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    program_code: Mapped[str] = mapped_column(String(32), index=True)
    policy_version: Mapped[str] = mapped_column(String(32))
    beneficiary_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    order_renewal_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_renewals.id"), nullable=True, index=True,
    )
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    period_key: Mapped[str] = mapped_column(String(7), index=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    rate_bps: Mapped[int] = mapped_column(Integer)
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    policy_snapshot: Mapped[dict] = mapped_column(JSON)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    settled_ledger_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
