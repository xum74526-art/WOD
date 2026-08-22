from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class NotificationOut(OrmModel):
    id: int
    title: str
    content: str | None = None
    title_en: str | None = None
    content_en: str | None = None
    type: str
    action_url: str | None = None
    is_read: bool
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
