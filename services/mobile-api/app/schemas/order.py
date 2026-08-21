from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel


class OrderCreateIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)
    cycle_days: int = 30
    purchase_type: str | None = "usage"  # usage / holding
    client_request_id: str | None = Field(default=None, min_length=12, max_length=64)


class OrderOut(OrmModel):
    id: int
    order_no: str
    client_request_id: str | None = None
    product_id: int
    quantity: int = 1
    cycle_days: int
    amount: float
    status: str
    purchase_type: str | None = "usage"
    ssh_info: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    created_at: datetime | None = None
    product_name: str | None = None
    gpu_model: str | None = None
    asset_id: int | None = None
    market_source: str | None = None
    fulfillment_status: str | None = None
    accumulated_revenue: float = 0
    remaining_days: int | None = None
