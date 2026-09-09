from typing import Literal

from fastapi import APIRouter, Query

from app.schemas.platform import AppReleaseResponse
from app.services.app_release import app_release
from app.services.trade_mode import platform_capabilities
from app.utils.response import success


router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/capabilities")
def capabilities():
    """Public, fail-closed capability discovery for every client generation."""

    return success(platform_capabilities())


@router.get("/app-release", response_model=AppReleaseResponse)
def release(platform: Literal["android", "ios"] = Query(...)):
    """Return trusted public release metadata without requiring a session."""

    return success(app_release(platform))
