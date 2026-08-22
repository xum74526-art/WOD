from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RechargePaymentCreateIn(BaseModel):
    amount_cny: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_type: Literal["alipay", "wxpay"]

    @field_validator("amount_cny")
    @classmethod
    def normalize_money(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
