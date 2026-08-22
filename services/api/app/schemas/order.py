from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel


class OrderCreateIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)
    hours: int | None = Field(default=None, ge=1, le=720)
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    purchase_type: str | None = "usage"  # usage / holding
    client_request_id: str | None = Field(default=None, min_length=12, max_length=64)


class OrderRenewIn(BaseModel):
    hours: int | None = Field(default=None, ge=1, le=720)
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    client_request_id: str = Field(min_length=12, max_length=64)


class OrderOut(OrmModel):
    id: int
    order_no: str
    client_request_id: str | None = None
    product_id: int
    quantity: int = 1
    cycle_days: int | None = None
    purchase_hours: int | None = None
    duration_hours: int | None = None
    purchase_unit: str | None = None
    billing_unit: str | None = None
    created_platform: str = "legacy"
    last_modified_platform: str = "legacy"
    amount: float
    amount_card_hours: float | None = None
    price_cny_per_gpu_hour: float | None = None
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
    remaining_hours: int | None = None
