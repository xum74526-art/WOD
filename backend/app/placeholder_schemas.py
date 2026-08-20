from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HostedDeviceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    device_type: Literal["gpu_server", "workstation", "other"] = "gpu_server"
    serial_number: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)


class WithdrawalCreateIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3,8}$")
    bank_account_id: int = Field(gt=0)


class ReferralInvitationCreateIn(BaseModel):
    channel: Literal["email", "sms", "link"] = "link"
    destination: str | None = Field(default=None, max_length=255)


class CouponRedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class BankAccountBindIn(BaseModel):
    return_path: str = Field(default="/account/bank-accounts", min_length=1, max_length=256)

    @field_validator("return_path")
    @classmethod
    def safe_return_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("return_path must be a local path")
        return value


class AddressCreateIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CN", pattern=r"^[A-Z]{2}$")
    province: str = Field(min_length=1, max_length=64)
    city: str = Field(min_length=1, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address_line: str = Field(min_length=2, max_length=255)
    postal_code: str | None = Field(default=None, max_length=24)
    is_default: bool = False


class AddressUpdateIn(BaseModel):
    recipient_name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    province: str | None = Field(default=None, min_length=1, max_length=64)
    city: str | None = Field(default=None, min_length=1, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address_line: str | None = Field(default=None, min_length=2, max_length=255)
    postal_code: str | None = Field(default=None, max_length=24)


class DisputeCreateIn(BaseModel):
    order_id: int = Field(gt=0)
    reason: Literal[
        "not_delivered",
        "service_unavailable",
        "configuration_mismatch",
        "billing_issue",
        "other",
    ]
    description: str = Field(min_length=10, max_length=2000)
    attachment_object_ids: list[int] = Field(default_factory=list, max_length=10)


class ProvisioningStartIn(BaseModel):
    order_id: int = Field(gt=0)
    template_id: str | None = Field(default=None, max_length=128)
    configuration: dict[str, str | int | bool] = Field(default_factory=dict)


class CredentialIssueIn(BaseModel):
    credential_type: Literal["ssh", "rdp", "api_token", "console"]
    expires_in_minutes: int = Field(default=60, ge=5, le=10080)


class MeteringSyncIn(BaseModel):
    period_start: datetime
    period_end: datetime

    @field_validator("period_end")
    @classmethod
    def valid_period_end(cls, value: datetime, info):
        start = info.data.get("period_start")
        if start is not None and value <= start:
            raise ValueError("period_end must be after period_start")
        return value


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)


class TeamInvitationCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: Literal["owner", "admin", "member", "viewer"] = "member"


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    scopes: list[Literal["market:read", "orders:read", "orders:write", "assets:read"]] = Field(
        default_factory=lambda: ["market:read"], min_length=1, max_length=8
    )
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


class SupplierSettingsUpdateIn(BaseModel):
    store_name: str = Field(min_length=2, max_length=128)
    contact_name: str = Field(min_length=2, max_length=64)
    contact_phone: str = Field(min_length=6, max_length=32)
    service_regions: list[str] = Field(default_factory=list, max_length=20)


class AssetRenewalCreateIn(BaseModel):
    period_count: int = Field(default=1, ge=1, le=36)
    period_unit: Literal["day", "month"] = "month"
    payment_method: Literal["wallet", "payment_provider"] = "wallet"
