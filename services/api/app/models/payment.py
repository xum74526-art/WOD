from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentOrder(Base):
    """One provider payment mapped to one wallet credit.

    Money is persisted in CNY while ``card_hours`` records the immutable
    customer-facing conversion result.  ``credited_at`` is the idempotency
    boundary: a verified provider notification and wallet credit are committed
    in the same database transaction.
    """

    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="mapay")
    provider_trade_no: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    # A validated provider URL makes reopening a checkout token idempotent.
    provider_checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Recorded before outbound create I/O so other workers can distinguish an
    # in-flight request from an abandoned/uncertain upstream order.
    checkout_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    card_hour_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    checkout_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
