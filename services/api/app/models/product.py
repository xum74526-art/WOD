from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    gpu_model: Mapped[str] = mapped_column(String(64))
    memory: Mapped[str] = mapped_column(String(32))
    cuda: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # CNY/h 展示价
    cycle: Mapped[list | None] = mapped_column(JSON, nullable=True)
    desc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 地区
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    region_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Vast 行情价格元数据
    source_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)  # USD/h
    source_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stock: Mapped[int] = mapped_column(default=0)  # 可租数量
    reliability: Mapped[float] = mapped_column(default=99.5)  # 稳定性
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="on")  # on/off
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
