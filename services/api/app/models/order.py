from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, String, DateTime, Numeric, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "client_request_id", name="uq_orders_user_client_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    # New KAI purchases use an explicit integer-hour duration. ``cycle_days``
    # remains untouched for legacy orders and first-party merchant contracts.
    purchase_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_days: Mapped[int] = mapped_column(Integer, default=30)
    # Trusted attribution copied from the authenticated server-side session.
    # Historical rows are migrated to ``legacy`` instead of being guessed.
    created_platform: Mapped[str] = mapped_column(String(16), default="legacy", index=True)
    last_modified_platform: Mapped[str] = mapped_column(String(16), default="legacy", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    coupon_id: Mapped[int | None] = mapped_column(
        ForeignKey("coupons.id"), nullable=True, index=True,
    )
    coupon_discount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0",
    )
    status: Mapped[str] = mapped_column(String(16), default="running")  # paid/delivering/disputed/completed/running/done/canceled
    purchase_type: Mapped[str] = mapped_column(String(16), default="usage")  # usage(使用) / holding(持有)
    product_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Existing rows remain NULL after schema upgrade and require explicit stock
    # reconciliation. New reserved-fund orders use the versioned lifecycle.
    lifecycle_policy_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="reserved-v1",
    )
    ssh_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # 字段级加密的 SSH 连接信息
    delivery_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmation_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stock_released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispute_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispute_resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dispute_resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispute_resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispute_resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
