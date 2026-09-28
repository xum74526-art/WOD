from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import OrmModel


class OnboardingIn(BaseModel):
    entity_type: Literal["personal", "company"] = "personal"
    contact: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=5, max_length=20)
    device_model: str = Field(min_length=1, max_length=128)
    device_count: int = Field(default=1, ge=1, le=10000)
    location: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("contact", "phone", "device_model", "location", "remark", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()


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
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_platform: str = "legacy"
    last_modified_platform: str = "legacy"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OnboardingReviewIn(BaseModel):
    status: Literal["contacted", "approved", "rejected"]
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def rejection_requires_note(self):
        if self.status == "rejected" and not self.note:
            raise ValueError("驳回时必须填写处理说明")
        return self
