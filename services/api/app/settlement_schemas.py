from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.buy_request_schemas import InputModel, VersionedActionIn


class SupplierWithdrawalCreateIn(InputModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Literal["CNY"] = "CNY"
    beneficiary_name: str = Field(min_length=2, max_length=64)
    bank_name: str = Field(min_length=2, max_length=128)
    bank_account_no: str = Field(pattern=r"^[0-9]{6,32}$")


class WithdrawalReviewIn(VersionedActionIn):
    note: str | None = Field(default=None, max_length=500)


class WithdrawalRejectIn(VersionedActionIn):
    note: str = Field(min_length=2, max_length=500)


class WithdrawalCompleteIn(VersionedActionIn):
    payment_reference: str = Field(min_length=2, max_length=128)
    note: str | None = Field(default=None, max_length=500)
