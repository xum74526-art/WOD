from pydantic import BaseModel, EmailStr, Field


class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class CommentReportIn(BaseModel):
    reason: str = Field(min_length=2, max_length=32)
    detail: str | None = Field(default=None, max_length=300)


class CommentModerationIn(BaseModel):
    status: str = Field(pattern="^(visible|hidden|pending_manual|deleted)$")
    violation_category: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=255)


class EmailRegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    code: str | None = None


class EmailLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordRegisterIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=64)
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PasswordLoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class TokenLoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class TokenRegisterIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=64)
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class KaiStartIn(BaseModel):
    intent: str = Field(pattern="^(login|register)$")


class KaiExchangeIn(BaseModel):
    ticket: str = Field(min_length=8, max_length=1024)


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class EmailVerificationConfirmIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AccountProfileUpdateIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=64)


class CodeRequestIn(BaseModel):
    destination: str = Field(min_length=3, max_length=255)
    purpose: str = Field(pattern="^(login|register)$")


class PhoneAuthIn(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    code: str | None = None


class SupplierApplicationIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=128)
    contact_name: str = Field(min_length=2, max_length=64)
    contact_phone: str = Field(min_length=6, max_length=32)
    region: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)


class SupplierApprovalIn(BaseModel):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class SupplierRejectionIn(BaseModel):
    version: int = Field(ge=1)
    note: str = Field(min_length=2, max_length=1000)
