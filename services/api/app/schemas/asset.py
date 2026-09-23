from datetime import datetime

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel, ResponseBase


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
    audited_earnings_enabled: bool = True
    rebate_status: str | None = None
    rebate_amount: float | None = None
    pending_rebate: float = 0
    settled_rebate: float = 0
    reward_service_enabled: bool = False
    revenue_settlement_enabled: bool = False
    historical_test_revenue: float = 0
    historical_test_reward: float = 0
    rebate_info: dict | None = None
    remaining_days: int | None = None
    current_price: float | None = None
    current_unit_price: float | None = None
    buy_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    price_observed_at: datetime | None = None
    can_sell: bool = False
    trading_unavailable_reason: str | None = None


class AssetSellIn(BaseModel):
    client_request_id: str = Field(
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    expected_unit_price_card_hours: Decimal = Field(gt=0)


class AssetSummary(BaseModel):
    total_value: float
    wallet_balance: float
    pending_revenue: float
    revenue_rate: float
    audited_earnings_enabled: bool = True
    revenue_settlement_enabled: bool = False
    historical_test_revenue: float = 0
    items: list[AssetOut]


class AssetResponse(ResponseBase):
    data: AssetOut


class AssetSummaryResponse(ResponseBase):
    data: AssetSummary
