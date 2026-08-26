from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OrmModel


class OrderCreateIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)
    hours: int | None = Field(default=None, ge=1, le=720)
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    expected_unit_price_card_hours: Decimal | None = None
    purchase_type: str | None = "usage"  # usage / holding
    client_request_id: str | None = Field(default=None, min_length=12, max_length=64)


class OrderRenewIn(BaseModel):
    hours: int | None = Field(default=None, ge=1, le=720)
    cycle_days: int | None = Field(default=None, ge=1, le=3650)
    client_request_id: str = Field(min_length=12, max_length=64)


class OrderDisputeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 5:
            raise ValueError("争议原因至少填写 5 个字符")
        return normalized


class OrderDeliverIn(BaseModel):
    ssh_info: str = Field(min_length=5, max_length=2000)

    @field_validator("ssh_info")
    @classmethod
    def normalize_ssh_info(cls, value: str) -> str:
        return value.strip()


class OrderDisputeResolveIn(BaseModel):
    action: Literal["refund", "release"]
    note: str = Field(min_length=5, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 5:
            raise ValueError("处理说明至少填写 5 个字符")
        return normalized


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
    product_snapshot: dict | None = None
    ssh_info: str | None = None
    delivery_due_at: datetime | None = None
    delivered_at: datetime | None = None
    confirmation_due_at: datetime | None = None
    confirmed_at: datetime | None = None
    canceled_at: datetime | None = None
    stock_released_at: datetime | None = None
    disputed_at: datetime | None = None
    dispute_due_at: datetime | None = None
    dispute_reason: str | None = None
    dispute_resolution: str | None = None
    dispute_resolution_note: str | None = None
    dispute_resolved_at: datetime | None = None
    can_cancel: bool = False
    can_confirm: bool = False
    can_dispute: bool = False
    can_deliver: bool = False
    can_renew: bool = False
    start_at: datetime | None = None
    end_at: datetime | None = None
    created_at: datetime | None = None
    product_name: str | None = None
    gpu_model: str | None = None
    asset_id: int | None = None
    market_source: str | None = None
    seller_type: str | None = None
    seller_name: str | None = None
    fulfillment_mode: str | None = None
    fulfillment_status: str | None = None
    accumulated_revenue: float = 0
    remaining_days: int | None = None
    remaining_hours: int | None = None
