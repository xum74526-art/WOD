from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel


class ProductOut(OrmModel):
    id: int
    name: str
    gpu_model: str
    memory: str
    cuda: str | None = None
    price: float
    cycle: list[int] | None = None
    billing_unit: str | None = None
    price_currency: str | None = None
    price_cny_per_gpu_hour: float | None = None
    price_card_hours_per_gpu_hour: float | None = None
    wallet_charge_unit: str | None = None
    purchase_unit: str | None = None
    purchase_hour_options: list[int] = Field(default_factory=list)
    min_purchase_hours: int | None = None
    max_purchase_hours: int | None = None
    desc: str | None = None
    image_url: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    city: str | None = None
    market_source: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    supplier_rating: float | None = None
    supplier_order_count: int | None = None
    seller_type: Literal["kai_self_operated", "merchant"] | None = None
    seller_name: str | None = None
    fulfillment_mode: Literal["platform_manual", "merchant_manual"] | None = None
    resource_claim_source: Literal["kai_published", "merchant_declared"] | None = None
    assurance_label: str | None = None
    assurance_description: str | None = None
    external_product_id: str | None = None
    stock_semantics: str | None = None
    source_max_configurable_quantity: int | None = None
    platform_stock_cap: int | None = None
    platform_stock_remaining: int | None = None
    source_price: float | None = None
    exchange_rate: float | None = None
    price_updated_at: datetime | None = None
    status: str
    daily_revenue: float | None = None
    revenue_estimate_available: bool = False
    interaction_mode: Literal["direct_trade", "matchmaking", "history_only"] = "history_only"
    inquiry_available: bool = False
    purchasable: bool = False
    purchase_unavailable_reason: str | None = None
    stock: int | None = None
    reported_stock: int | None = None
    max_configurable_quantity: int | None = None
    market_source_status: str | None = None
    is_market_current: bool = False
    stability: float = 99.0
    tags: list = Field(default_factory=list)
    created_at: datetime | None = None


class PricePoint(BaseModel):
    date: str
    price: float


class RegionOut(BaseModel):
    code: str
    name: str
