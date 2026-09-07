"""Field-level encryption helpers for sensitive local data."""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import DEFAULT_SECRET_KEY, settings

_PREFIX = "enc:v1:"


def sensitive_security_errors() -> tuple[str, ...]:
    """Return non-secret configuration errors for PII-bearing capabilities."""
    problems: list[str] = []
    secret = settings.SECRET_KEY.strip()
    configured_key = settings.SENSITIVE_DATA_KEY.strip()
    if not secret or hmac.compare_digest(secret, DEFAULT_SECRET_KEY):
        problems.append("default_secret_key")
    if not configured_key:
        problems.append("missing_sensitive_data_key")
    else:
        try:
            key_bytes = configured_key.encode("ascii")
            Fernet(key_bytes)
            derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
            if hmac.compare_digest(key_bytes, derived):
                problems.append("sensitive_data_key_not_independent")
        except (UnicodeEncodeError, ValueError):
            problems.append("invalid_sensitive_data_key")
    return tuple(problems)


def sensitive_capability_enabled(configured: bool) -> bool:
    return bool(configured) and not sensitive_security_errors()


def assert_sensitive_capabilities_secure() -> None:
    enabled = [
        name for name, value in (
            ("ID_OCR_ENABLED", settings.ID_OCR_ENABLED),
            ("MANUAL_BANK_CARD_ENABLED", settings.MANUAL_BANK_CARD_ENABLED),
            ("MANUAL_PAYOUT_ENABLED", settings.MANUAL_PAYOUT_ENABLED),
            ("ACCOUNT_RECOVERY_EMAIL_ENABLED", settings.ACCOUNT_RECOVERY_EMAIL_ENABLED),
        ) if value
    ]
    if not enabled:
        return
    problems = sensitive_security_errors()
    if problems:
        raise RuntimeError(
            "Sensitive capabilities require a non-default SECRET_KEY and an "
            "independent valid SENSITIVE_DATA_KEY; enabled="
            + ",".join(enabled)
            + "; errors="
            + ",".join(problems)
        )


def _key() -> bytes:
    configured = settings.SENSITIVE_DATA_KEY.strip()
    if configured:
        return configured.encode("ascii")
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def protect(value: str | None) -> str | None:
    if value is None or value == "" or value.startswith(_PREFIX):
        return value
    token = Fernet(_key()).encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def reveal(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        # Legacy local rows remain readable and are encrypted on the next write.
        return value
    try:
        token = value[len(_PREFIX):].encode("ascii")
        return Fernet(_key()).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def fingerprint(value: str) -> str:
    normalized = "".join(value.split()).upper()
    material = ("wod:sensitive-fingerprint:v1|" + normalized).encode("utf-8")
    return hmac.new(_key(), material, hashlib.sha256).hexdigest()


def mask_id_card(value: str) -> str:
    plain = reveal(value)
    if len(plain) < 6:
        return ""
    return plain[:4] + "************" + plain[-2:]


def mask_bank_card(value: str) -> str:
    plain = "".join(reveal(value).split())
    if len(plain) < 8:
        return ""
    return plain[:4] + " **** **** " + plain[-4:]


def last_four(value: str) -> str:
    plain = "".join(reveal(value).split())
    return plain[-4:] if len(plain) >= 4 else ""
