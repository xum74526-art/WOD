from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class RevenueSummary(BaseModel):
    today: float
    total: float
    rate: float


class RevenuePoint(BaseModel):
    date: str
    amount: float


class RevenueRecord(OrmModel):
    id: int
    amount: float
    date: str | None = None
    created_at: datetime | None = None
