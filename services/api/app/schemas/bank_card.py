from datetime import datetime

import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OrmModel


class BankCardIn(BaseModel):
    bank_name: str | None = Field(default=None, max_length=64)  # 可选，自动识别
    card_number: str = Field(min_length=12, max_length=32)
    holder: str = Field(min_length=2, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    is_default: bool = False

    @field_validator("card_number")
    @classmethod
    def card_number_digits_and_spaces_only(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9 ]+", value):
            raise ValueError("card number accepts digits and spaces only")
        normalized = value.replace(" ", "")
        if not 12 <= len(normalized) <= 19:
            raise ValueError("card number length must be 12-19 digits")
        return normalized

    @field_validator("holder")
    @classmethod
    def clean_holder(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or any(ord(ch) < 32 for ch in value):
            raise ValueError("invalid card holder")
        return value

    @field_validator("bank_name")
    @classmethod
    def clean_bank_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2 or any(ord(ch) < 32 for ch in value):
            raise ValueError("invalid bank name")
        return value

    @field_validator("phone")
    @classmethod
    def phone_digits_only(cls, value: str | None) -> str | None:
        if value in {None, ""}:
            return None
        if not re.fullmatch(r"1\d{10}", value):
            raise ValueError("invalid phone")
        return value


class BankCardOut(OrmModel):
    id: int
    bank_name: str
    card_number: str
    card_last4: str | None = None
    holder: str
    phone: str | None = None
    is_default: bool
    status: str = "registered"
    verification_mode: str = "format_only"
    bank_verified: bool = False
    reject_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None
