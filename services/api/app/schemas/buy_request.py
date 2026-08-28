from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QuoteRevisionIn(BaseModel):
    unit_price: float | None = Field(default=None, ge=0)
    total_price: float = Field(ge=0)
    currency: str = Field(default="CNY", min_length=1, max_length=8)
    available_at: datetime | None = None
    message: str | None = Field(default=None, max_length=1000)
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


class DealActionIn(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)


class DealReasonIn(DealActionIn):
    reason: str | None = Field(default=None, max_length=1000)


class DeliveryIssueIn(DealActionIn):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class MatchmakingCredentialIn(DealActionIn):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64)
    auth_type: Literal["password", "private_key"]
    secret: str = Field(min_length=1, max_length=20000)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("host", "username", "secret")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be blank")
        return normalized

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        normalized = value.strip().strip("[]")
        if (
            normalized.lower() == "localhost"
            or "/" in normalized
            or "\\" in normalized
            or ".." in normalized
            or any(char.isspace() for char in normalized)
        ):
            raise ValueError("invalid host")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:")
        if not normalized or any(char not in allowed for char in normalized):
            raise ValueError("invalid host")
        return normalized
