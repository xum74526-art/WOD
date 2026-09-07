from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.email_address import normalize_email


class KaiStartIn(BaseModel):
    intent: Literal["login", "register", "recover"] = "login"
    return_url: str | None = Field(default=None, max_length=1024)
    client_id: str | None = Field(default=None, min_length=1, max_length=64)


class KaiBindStartIn(BaseModel):
    return_url: str | None = Field(default=None, max_length=1024)


class KaiTicketIn(BaseModel):
    ticket: str = Field(..., min_length=20, max_length=256)


class RecoveryEmailVerificationRequestIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    current_password: str = Field(..., min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class RecoveryTokenIn(BaseModel):
    token: str = Field(..., min_length=32, max_length=256)


class PasswordResetRequestIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirmIn(RecoveryTokenIn):
    password: str = Field(..., min_length=8, max_length=64)
