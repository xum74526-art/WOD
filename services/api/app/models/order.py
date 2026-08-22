from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Integer, Text, UniqueConstraint, func
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
    status: Mapped[str] = mapped_column(String(16), default="running")  # paid(pending delivery)/delivering/completed/disputed/canceled
    purchase_type: Mapped[str] = mapped_column(String(16), default="usage")  # usage(使用) / holding(持有)
    ssh_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # 字段级加密的 SSH 连接信息
    start_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
