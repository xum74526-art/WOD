from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class AssetOut(OrmModel):
    id: int
    product_id: int
    order_id: int | None = None
    quantity: int
    value: float
    unit_value: float | None = None
    daily_rate: float
    status: str
    purchase_type: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    created_at: datetime | None = None
    product_name: str | None = None
    gpu_model: str | None = None
    today_revenue: float = 0
    accumulated_revenue: float = 0
    remaining_days: int | None = None


class AssetSummary(BaseModel):
    total_value: float
    wallet_balance: float
    pending_revenue: float
    revenue_rate: float
    items: list[AssetOut]
