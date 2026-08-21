from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BuyRequest(Base):
    __tablename__ = "buy_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(16), index=True)  # online/offline
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    gpu_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    billing_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="published", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    legacy_offline_purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("offline_purchases.id"), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BuyRequestQuote(Base):
    __tablename__ = "buy_request_quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    buy_request_id: Mapped[int] = mapped_column(ForeignKey("buy_requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    available_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
