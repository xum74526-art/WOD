from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class AddressIn(BaseModel):
    name: str
    phone: str
    province: str
    city: str
    district: str
    detail: str
    label: str | None = None
    is_default: bool = False


class AddressUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    detail: str | None = None
    label: str | None = None
    is_default: bool | None = None


class AddressOut(OrmModel):
    id: int
    name: str
    phone: str
    province: str
    city: str
    district: str
    detail: str
    label: str | None = None
    is_default: bool
    created_at: datetime | None = None
