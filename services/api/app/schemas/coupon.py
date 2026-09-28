from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OrmModel


class CouponOut(OrmModel):
    id: int
    campaign_id: int | None = None
    product_id: int | None = None
    name: str
    amount: float
    min_amount: float
    status: Literal["available", "used", "expired"]
    expires_at: datetime | None = None
    redeemed_at: datetime | None = None
    used_at: datetime | None = None
    used_order_id: int | None = None
    created_platform: str = "legacy"
    version: int = 1
    created_at: datetime | None = None


class RedeemIn(BaseModel):
    code: str = Field(min_length=8, max_length=48)

    @field_validator("code")
    @classmethod
    def normalize_code_input(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("请输入兑换码")
        return normalized


class CouponCampaignCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    amount: Decimal = Field(gt=0, le=Decimal("1000000"), decimal_places=6)
    min_amount: Decimal = Field(ge=0, le=Decimal("100000000"), decimal_places=6)
    max_redemptions: int = Field(ge=1, le=1_000_000)
    coupon_ttl_days: int = Field(default=30, ge=1, le=3650)
    product_id: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    expires_at: datetime
    code: str | None = Field(default=None, min_length=8, max_length=48)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("活动名称至少填写 2 个字符")
        return normalized

class CouponCampaignStatusIn(BaseModel):
    status: Literal["active", "disabled"]
    expected_version: int = Field(ge=1)


class CouponCampaignOut(OrmModel):
    id: int
    code_hint: str
    name: str
    amount: float
    min_amount: float
    product_id: int | None = None
    max_redemptions: int
    redeemed_count: int
    coupon_ttl_days: int
    status: Literal["active", "scheduled", "disabled", "expired", "exhausted"]
    starts_at: datetime | None = None
    expires_at: datetime
    created_by: int
    last_modified_by: int
    created_platform: str
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CouponCampaignCreatedOut(CouponCampaignOut):
    code: str
