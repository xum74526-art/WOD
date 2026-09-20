from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


# The manual-payout database columns intentionally remain naive UTC DateTime
# values for compatibility with existing rows. Incoming payment attestations
# must nevertheless identify an instant unambiguously before the service
# converts them to that storage representation.
PayoutPaidAt = AwareDatetime


class WithdrawalCreateIn(BaseModel):
    amount_card_hours: Decimal
    bank_card_id: int = Field(gt=0)
    client_request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("amount_card_hours")
    @classmethod
    def amount_is_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value


class FinanceReviewIn(BaseModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=255)


class ApproveWithdrawalIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RejectWithdrawalIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("reason is required")
        return value


class FailedWithdrawalIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("reason is required")
        return value


class PaymentInstructionsOut(BaseModel):
    order_id: int
    order_no: str
    bank_name: str
    card_number: str
    holder: str
    phone: str
    amount_cny: float
    verification_mode: Literal["format_only"]
    bank_verified: Literal[False]
    reveal_token: str
    reveal_expires_at: datetime
    notice: str


class PaymentInstructionsResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: PaymentInstructionsOut
