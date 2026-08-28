from fastapi import APIRouter

from app.services.trade_mode import platform_capabilities
from app.utils.response import success


router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/capabilities")
def capabilities():
    """Public, fail-closed capability discovery for every client generation."""

    return success(platform_capabilities())
