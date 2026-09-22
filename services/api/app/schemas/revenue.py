from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class RevenueSummary(BaseModel):
    today: float
    total: float
    rate: float
    settled_rebate_total: float = 0
    settled_rebate_today: float = 0
    pending_rebate: float = 0
    holding_realized_pnl: float = 0
    holding_realized_pnl_today: float = 0
    holding_unrealized_pnl: float = 0
    holding_unrealized_pnl_rate: float = 0
    holding_active_assets: int = 0
    holding_priced_assets: int = 0
    audited_earnings_enabled: bool = True
    revenue_settlement_enabled: bool = False
    historical_test_total: float = 0


class RevenuePoint(BaseModel):
    date: str
    amount: float


class RevenueRecord(OrmModel):
    id: int
    record_key: str | None = None
    source_type: str | None = None
    asset_id: int | None = None
    amount: float
    date: str | None = None
    created_at: datetime | None = None
