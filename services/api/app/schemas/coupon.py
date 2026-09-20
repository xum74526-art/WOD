from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class CouponOut(OrmModel):
    id: int
    name: str
    amount: float
    min_amount: float
    status: str
    expires_at: datetime | None = None
    created_at: datetime | None = None


class RedeemIn(BaseModel):
    code: str
