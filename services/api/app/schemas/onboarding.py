from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class OnboardingIn(BaseModel):
    entity_type: str = "personal"  # personal/company
    contact: str
    phone: str
    device_model: str
    device_count: int = 1
    location: str | None = None
    remark: str | None = None


class OnboardingOut(OrmModel):
    id: int
    entity_type: str
    contact: str
    phone: str
    device_model: str
    device_count: int
    location: str | None = None
    remark: str | None = None
    status: str
    created_at: datetime | None = None
