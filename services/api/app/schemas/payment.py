from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RechargePaymentCreateIn(BaseModel):
    amount_cny: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_type: Literal["alipay", "wxpay"]
    # Optional during the installed-client transition.  Current clients must
    # reuse this value when retrying the same recharge intent.
    client_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )

    @field_validator("amount_cny")
    @classmethod
    def normalize_money(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class PaymentReviewDecisionIn(BaseModel):
    action: Literal["credit", "refund"]
    note: str = Field(min_length=3, max_length=500)
    client_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class PaymentRefundCreateIn(BaseModel):
    client_request_id: str = Field(
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    reason: str = Field(min_length=3, max_length=500)


class PaymentRefundResolveIn(BaseModel):
    outcome: Literal["succeeded", "failed"]
    note: str = Field(min_length=3, max_length=500)
