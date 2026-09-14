from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OrmModel


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    phone: str = Field(..., pattern=r"^1\d{10}$")
    password: str = Field(..., min_length=6, max_length=64)
    invite_code: str | None = None
    captcha_key: str = Field(..., min_length=1, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=6)
    client_id: str | None = Field(default=None, min_length=1, max_length=64)


class LoginIn(BaseModel):
    phone: str = Field(..., pattern=r"^1\d{10}$")
    password: str = Field(..., min_length=1, max_length=64)
    client_id: str | None = Field(default=None, min_length=1, max_length=64)


class UserOut(OrmModel):
    id: int
    username: str
    phone: str | None = None
    phone_bound: bool = False
    avatar: str | None = None
    role: str | None = "personal"
    supplier_status: str | None = "none"
    created_at: datetime | None = None

    @model_validator(mode="after")
    def hide_internal_phone(self):
        if not self.phone_bound:
            self.phone = None
        return self


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileUpdateIn(BaseModel):
    username: str | None = None
    avatar: str | None = None
    phone: str | None = None


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=64)
