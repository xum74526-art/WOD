from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    # 纯逻辑外键，不设约束以避免与 orders 的循环依赖
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/expired/sold/used
    purchase_type: Mapped[str] = mapped_column(String(16), default="usage")  # usage; holding is retained only for legacy rows
    sell_price: Mapped[float | None] = mapped_column(default=None)
    rebate_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # pending/rewarded/forfeited
    rebate_amount: Mapped[float | None] = mapped_column(default=None)  # 预计返佣金额
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
