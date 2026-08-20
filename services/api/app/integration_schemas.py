from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PaymentIntentCreateIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3,8}$")
    purpose: Literal["wallet_recharge", "order_payment"] = "wallet_recharge"
    order_id: int | None = Field(default=None, gt=0)
    return_path: str = Field(default="/account/wallet", min_length=1, max_length=256)
    payment_channel: Literal[
        "alipay_pc_direct", "alipay_wap", "wx_wap", "upacp_pc", "upacp_wap"
    ] | None = None

    @field_validator("return_path")
    @classmethod
    def safe_return_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("return_path must be a local path")
        return value


class KycStartIn(BaseModel):
    verification_type: Literal["individual", "business"] = "individual"
    country_code: str = Field(default="CN", pattern=r"^[A-Z]{2}$")
    return_path: str = Field(default="/account/verification", min_length=1, max_length=256)

    @field_validator("return_path")
    @classmethod
    def safe_return_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("return_path must be a local path")
        return value


class UploadInitIn(BaseModel):
    category: Literal[
        "kyc_document",
        "supplier_document",
        "contract",
        "delivery_artifact",
        "general_private",
    ]
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=128)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    kyc_application_id: int | None = Field(default=None, gt=0)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
            raise ValueError("filename must not contain path separators")
        return cleaned


class UploadCompleteIn(BaseModel):
    upload_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    etag: str | None = Field(default=None, max_length=256)
