from typing import Literal

from pydantic import BaseModel


class AppReleaseInfo(BaseModel):
    platform: Literal["android", "ios"]
    application_id: str | None = None
    available: bool
    latest_version_name: str | None = None
    latest_version_code: int | None = None
    update_url: str | None = None
    release_notes_zh: list[str]
    release_notes_en: list[str]


class AppReleaseResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: AppReleaseInfo
