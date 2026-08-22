from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Integer, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OfflinePurchase(Base):
    __tablename__ = "offline_purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_model: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    contact: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20))
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="submitted")  # submitted/contacted/done/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
