from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class ProductOut(OrmModel):
    id: int
    name: str
    gpu_model: str
    memory: str
    cuda: str | None = None
    price: float
    cycle: list[int] | None = None
    desc: str | None = None
    image_url: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    city: str | None = None
    source_price: float | None = None
    exchange_rate: float | None = None
    price_updated_at: datetime | None = None
    status: str
    daily_revenue: float | None = None
    revenue_estimate_available: bool = False
    purchasable: bool = False
    purchase_unavailable_reason: str | None = None
    stock: int | None = None
    stability: float = 99.0
    tags: list = []
    created_at: datetime | None = None


class PricePoint(BaseModel):
    date: str
    price: float


class RegionOut(BaseModel):
    code: str
    name: str
