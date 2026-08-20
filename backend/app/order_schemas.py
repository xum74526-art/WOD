from typing import Literal

from pydantic import BaseModel, Field

from app.buy_request_schemas import VersionedActionIn


class OrderConfirmIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=1000)


class OrderCancelIn(VersionedActionIn):
    reason: str = Field(min_length=2, max_length=500)


class OrderDeliveryIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=1000)


class OrderCompleteIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=1000)


class DirectOrderCreateIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=64)
    duration_days: int = Field(ge=1, le=365)
    purchase_mode: Literal["usage"] = "usage"


class SandboxPaymentIn(VersionedActionIn):
    confirmation: Literal["LOCAL_TEST_PAYMENT"]


class SandboxWorkloadIn(BaseModel):
    iterations: int = Field(default=25000, ge=1000, le=200000)


class SandboxFinishIn(VersionedActionIn):
    pass
