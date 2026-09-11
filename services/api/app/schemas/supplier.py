from datetime import datetime

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OrmModel


class SupplierRegisterIn(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=128)
    contact: str = Field(..., min_length=2, max_length=64)
    phone: str = Field(..., pattern=r"^1\d{10}$")
    region: str | None = Field(default=None, max_length=64)
    desc: str | None = Field(default=None, max_length=255)


class SupplierProfileUpdateIn(BaseModel):
    company_name: str | None = Field(default=None, min_length=2, max_length=128)
    contact: str | None = Field(default=None, min_length=2, max_length=64)
    phone: str | None = Field(default=None, pattern=r"^1\d{10}$")
    region: str | None = Field(default=None, max_length=64)
    desc: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")
        for field in ("company_name", "contact", "phone"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为空")
        return self


class SupplierOut(OrmModel):
    id: int
    user_id: int
    company_name: str
    contact: str
    phone: str
    region: str | None = None
    desc: str | None = None
    status: str
    rating: float
    order_count: int
    created_at: datetime | None = None


class SupplierDeviceCreateIn(BaseModel):
    client_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    name: str = Field(..., min_length=2, max_length=128)
    gpu_model: str = Field(..., min_length=2, max_length=64)
    memory: str = Field(default="-", min_length=1, max_length=32)
    cuda: str | None = Field(default=None, max_length=32)
    price: Decimal = Field(..., ge=Decimal("0.0001"), le=100000)
    stock: int = Field(default=1, ge=0, le=100000)
    desc: str | None = Field(default="供应商上架", max_length=255)
    image_url: str | None = Field(default="/static/gpu/gpu.png", max_length=255)
    region_code: str = Field(default="east_china", min_length=1, max_length=32)
    region_name: str = Field(default="华东", min_length=1, max_length=32)
    city: str = Field(default="-", min_length=1, max_length=64)


class SupplierDeviceUpdateIn(BaseModel):
    price: Decimal | None = Field(default=None, ge=Decimal("0.0001"), le=100000)
    stock: int | None = Field(default=None, ge=0, le=100000)
    name: str | None = Field(default=None, min_length=2, max_length=128)
    status: Literal["on", "off"] | None = None
    # Optional during the rollout so already-installed clients keep working.
    # Current clients always send the version returned by the device list.
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set.difference({"expected_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self
