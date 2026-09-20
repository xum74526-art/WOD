from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderRenewal(Base):
    """Durable idempotency boundary and audit snapshot for one renewal."""

    __tablename__ = "order_renewals"
    __table_args__ = (
        UniqueConstraint("user_id", "client_request_id", name="uq_order_renewal_user_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    created_platform: Mapped[str] = mapped_column(String(16), default="legacy", index=True)
    purchase_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    previous_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_end_at: Mapped[datetime] = mapped_column(DateTime)
    total_amount_after: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    total_purchase_hours_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cycle_days_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
