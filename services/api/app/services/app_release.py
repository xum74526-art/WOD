from typing import Literal
from urllib.parse import urlsplit

from app.core.config import settings


MobilePlatform = Literal["android", "ios"]


def _release_notes(value: str) -> list[str]:
    return [part.strip()[:160] for part in value.split("|") if part.strip()][:5]


def _trusted_update_url(platform: MobilePlatform, value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment:
        return False
    if platform == "android":
        return (
            parsed.hostname == "wod.kai.com"
            and parsed.port is None
            and parsed.path.startswith("/download/")
            and parsed.path.lower().endswith(".apk")
        )
    return (
        parsed.hostname == "apps.apple.com"
        and parsed.port is None
        and parsed.path not in ("", "/")
    )


def app_release(platform: MobilePlatform) -> dict:
    prefix = f"APP_{platform.upper()}"
    enabled = bool(getattr(settings, f"{prefix}_RELEASE_ENABLED"))
    version_name = str(getattr(settings, f"{prefix}_LATEST_VERSION_NAME")).strip()
    version_code = int(getattr(settings, f"{prefix}_LATEST_VERSION_CODE"))
    update_url = str(getattr(settings, f"{prefix}_UPDATE_URL")).strip()

    available = (
        enabled
        and bool(version_name)
        and version_code > 0
        and _trusted_update_url(platform, update_url)
    )
    if not available:
        return {
            "platform": platform,
            "available": False,
            "latest_version_name": None,
            "latest_version_code": None,
            "update_url": None,
            "release_notes_zh": [],
            "release_notes_en": [],
        }

    return {
        "platform": platform,
        "available": True,
        "latest_version_name": version_name,
        "latest_version_code": version_code,
        "update_url": update_url,
        "release_notes_zh": _release_notes(getattr(settings, f"{prefix}_RELEASE_NOTES_ZH")),
        "release_notes_en": _release_notes(getattr(settings, f"{prefix}_RELEASE_NOTES_EN")),
    }
