from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class VersionIn(BaseModel):
    version: int = Field(ge=1)


class AddressCreateIn(BaseModel):
    label: str = Field(default="常用地址", min_length=1, max_length=32)
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
    version: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=32)
    recipient_name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    province: str | None = Field(default=None, min_length=1, max_length=64)
    city: str | None = Field(default=None, min_length=1, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    address_line: str | None = Field(default=None, min_length=2, max_length=255)
    postal_code: str | None = Field(default=None, max_length=24)
    is_default: bool | None = None


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


class DisputeResolveIn(BaseModel):
    version: int = Field(ge=1)
    status: Literal["under_review", "resolved", "rejected"]
    resolution: str | None = Field(default=None, max_length=2000)
    resolution_action: Literal["release_to_supplier", "refund_buyer"] | None = None

    @model_validator(mode="after")
    def validate_resolution_action(self):
        if self.status == "under_review" and self.resolution_action is not None:
            raise ValueError("处理中状态不能执行资金裁决")
        if self.status == "resolved" and self.resolution_action != "refund_buyer":
            raise ValueError("买家胜诉必须生成退款")
        if self.status == "rejected" and self.resolution_action != "release_to_supplier":
            raise ValueError("驳回争议必须继续商家结算")
        return self


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)


class TeamInvitationCreateIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


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
    introduction: str = Field(default="", max_length=2000)
    version: int | None = Field(default=None, ge=1)
