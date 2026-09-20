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


def _unavailable(platform: MobilePlatform, application_id: str | None = None) -> dict:
    return {
        "platform": platform,
        "application_id": application_id,
        "available": False,
        "latest_version_name": None,
        "latest_version_code": None,
        "update_url": None,
        "release_notes_zh": [],
        "release_notes_en": [],
    }


def _release_prefix(
    platform: MobilePlatform,
    application_id: str | None,
) -> tuple[str, str] | None:
    requested = (application_id or "").strip()
    if platform == "android":
        current_id = settings.APP_ANDROID_APPLICATION_ID.strip()
        legacy_id = settings.APP_ANDROID_LEGACY_APPLICATION_ID.strip()
        if requested == current_id:
            return "APP_ANDROID", current_id
        # Android clients released before the package rename did not send an
        # application_id. Keep them on the legacy artifact so they are never
        # told that a different package is an in-place update.
        if not requested or requested == legacy_id:
            return "APP_ANDROID_LEGACY", legacy_id
        return None

    current_id = settings.APP_IOS_APPLICATION_ID.strip()
    legacy_id = settings.APP_IOS_LEGACY_APPLICATION_ID.strip()
    if requested == current_id:
        return "APP_IOS", current_id
    # Older iOS builds also omitted application_id. Keep them isolated from a
    # future App Store listing that uses a different Bundle ID.
    if not requested or requested == legacy_id:
        return "APP_IOS_LEGACY", legacy_id
    return None


def app_release(platform: MobilePlatform, *, application_id: str | None = None) -> dict:
    selected = _release_prefix(platform, application_id)
    if selected is None:
        return _unavailable(platform)
    prefix, selected_application_id = selected
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
        return _unavailable(platform, selected_application_id)

    return {
        "platform": platform,
        "application_id": selected_application_id,
        "available": True,
        "latest_version_name": version_name,
        "latest_version_code": version_code,
        "update_url": update_url,
        "release_notes_zh": _release_notes(getattr(settings, f"{prefix}_RELEASE_NOTES_ZH")),
        "release_notes_en": _release_notes(getattr(settings, f"{prefix}_RELEASE_NOTES_EN")),
    }
