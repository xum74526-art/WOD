from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OrmModel


class NotificationOut(OrmModel):
    id: int
    title: str
    content: str | None = None
    title_en: str | None = None
    content_en: str | None = None
    template_key: str | None = None
    amount_cny: str | None = None
    type: str
    action_url: str | None = None
    is_read: bool
    expires_at: datetime | None = None
    created_at: datetime | None = None


class MajorAnnouncementOut(OrmModel):
    id: int
    title: str
    content: str
    title_en: str | None = None
    content_en: str | None = None
    action_url: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class NotificationPreferenceUpdate(BaseModel):
    order_enabled: bool | None = None
    device_enabled: bool | None = None
    revenue_enabled: bool | None = None
    wallet_enabled: bool | None = None
    system_enabled: bool | None = None


class NotificationPreferenceOut(OrmModel):
    order_enabled: bool
    device_enabled: bool
    revenue_enabled: bool
    wallet_enabled: bool
    system_enabled: bool
    updated_at: datetime | None = None


class NotificationBroadcastCreateIn(BaseModel):
    """Administrator announcement payload shared by the Web control plane.

    Action targets deliberately use the native ``/pages/`` namespace.  The
    Web adapter maps only its own allowlisted subset, while native clients can
    navigate the same target without opening an arbitrary external URL.
    """

    client_request_id: str = Field(
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=5000)
    title_en: str | None = Field(default=None, max_length=128)
    content_en: str | None = Field(default=None, max_length=5000)
    notification_type: Literal[
        "major_announcement",
        "system",
        "order",
        "device",
        "revenue",
        "wallet",
    ] = "system"
    action_url: str | None = Field(default=None, max_length=512)
    expires_at: datetime | None = None

    @field_validator("client_request_id", "title", "content", "title_en", "content_en", mode="before")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        return str(value).strip()

    @field_validator("action_url", mode="before")
    @classmethod
    def validate_action_url(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        if (
            not normalized.startswith("/pages/")
            or normalized.startswith("//")
            or any(ord(char) < 0x20 or char in "\\" for char in normalized)
            or "://" in normalized
            or "%" in normalized
            or any(segment == ".." for segment in normalized.split("/"))
        ):
            raise ValueError("跳转地址必须是安全的站内 /pages/ 路径")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("过期时间必须包含时区")
        normalized = value.astimezone(timezone.utc)
        if normalized <= datetime.now(timezone.utc):
            raise ValueError("过期时间必须晚于当前时间")
        return normalized


class NotificationBroadcastRevokeIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return str(value or "").strip()


class NotificationBroadcastOut(OrmModel):
    id: int
    client_request_id: str
    actor_user_id: int
    title: str
    content: str
    title_en: str | None = None
    content_en: str | None = None
    notification_type: str
    action_url: str | None = None
    audience: str
    status: str
    recipient_count: int
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: int | None = None
    revoke_reason: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class NotificationBroadcastPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[NotificationBroadcastOut]
