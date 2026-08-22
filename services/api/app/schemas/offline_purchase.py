from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class OfflinePurchaseIn(BaseModel):
    device_model: str
    quantity: int = 1
    budget: float = 0
    contact: str
    phone: str
    remark: str | None = None


class OfflinePurchaseOut(OrmModel):
    id: int
    device_model: str
    quantity: int
    budget: float
    contact: str
    phone: str
    remark: str | None = None
    status: str
    created_at: datetime | None = None
