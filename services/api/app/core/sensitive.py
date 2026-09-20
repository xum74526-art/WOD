"""Field-level encryption helpers for sensitive local data."""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import DEFAULT_SECRET_KEY, settings

_PREFIX = "enc:v1:"


class SensitiveDataDecryptionError(RuntimeError):
    """Raised when an encrypted value cannot be authenticated with known keys."""


def _legacy_secret_derived_key(secret: str | None = None) -> bytes:
    """Return the key used by releases that fell back to SECRET_KEY.

    This is intentionally decrypt-only compatibility. New ciphertext and
    fingerprints must always use the independently managed Fernet key.
    """
    source = settings.SECRET_KEY if secret is None else secret
    return base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())


def sensitive_security_errors() -> tuple[str, ...]:
    """Return non-secret configuration errors for sensitive-data storage."""
    problems: list[str] = []
    raw_secret = settings.SECRET_KEY
    secret = raw_secret.strip()
    configured_key = settings.SENSITIVE_DATA_KEY.strip()
    if not secret or hmac.compare_digest(secret, DEFAULT_SECRET_KEY):
        problems.append("default_secret_key")
    if not configured_key:
        problems.append("missing_sensitive_data_key")
    else:
        try:
            key_bytes = configured_key.encode("ascii")
            Fernet(key_bytes)
            known_insecure_keys = {
                _legacy_secret_derived_key(raw_secret),
                _legacy_secret_derived_key(secret),
                _legacy_secret_derived_key(DEFAULT_SECRET_KEY),
            }
            for reused_secret in (raw_secret, secret):
                try:
                    known_insecure_keys.add(reused_secret.encode("ascii"))
                except UnicodeEncodeError:
                    pass
            if any(
                hmac.compare_digest(key_bytes, insecure)
                for insecure in known_insecure_keys
            ):
                problems.append("sensitive_data_key_not_independent")
        except (UnicodeEncodeError, ValueError):
            problems.append("invalid_sensitive_data_key")
    return tuple(problems)


def sensitive_capability_enabled(configured: bool) -> bool:
    return bool(configured) and not sensitive_security_errors()


def assert_sensitive_storage_secure() -> None:
    """Fail closed unless persistent sensitive storage has independent keys."""
    problems = sensitive_security_errors()
    if problems:
        raise RuntimeError(
            "Sensitive storage requires a non-default SECRET_KEY and an "
            "independent valid SENSITIVE_DATA_KEY; errors="
            + ",".join(problems)
        )


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
    try:
        assert_sensitive_storage_secure()
    except RuntimeError as exc:
        raise RuntimeError(
            "Sensitive capabilities require secure storage; enabled="
            + ",".join(enabled)
            + "; "
            + str(exc)
        ) from exc


def _primary_fernet() -> Fernet:
    assert_sensitive_storage_secure()
    return Fernet(settings.SENSITIVE_DATA_KEY.strip().encode("ascii"))


def _decrypt(value: str) -> tuple[str, bool]:
    """Return plaintext and whether the legacy SECRET-derived key was used."""
    try:
        token = value[len(_PREFIX):].encode("ascii")
    except UnicodeEncodeError as exc:
        raise SensitiveDataDecryptionError(
            "Encrypted sensitive value is malformed and cannot be authenticated"
        ) from exc

    primary = _primary_fernet()
    try:
        return primary.decrypt(token).decode("utf-8"), False
    except (InvalidToken, UnicodeDecodeError):
        pass

    # Releases before the independent-key storage gate could persist enc:v1
    # using SHA-256(SECRET_KEY). Keep that key decrypt-only so a migration can
    # authenticate and immediately re-encrypt those rows with the primary key.
    legacy_keys = (
        _legacy_secret_derived_key(),
        _legacy_secret_derived_key(DEFAULT_SECRET_KEY),
    )
    last_error: Exception | None = None
    for legacy_key in dict.fromkeys(legacy_keys):
        try:
            return Fernet(legacy_key).decrypt(token).decode("utf-8"), True
        except (InvalidToken, UnicodeDecodeError) as exc:
            last_error = exc
    raise SensitiveDataDecryptionError(
        "Encrypted sensitive value cannot be authenticated with the configured "
        "or legacy key; refusing to alter the row"
    ) from last_error


def protect(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    primary = _primary_fernet()
    if value.startswith(_PREFIX):
        plaintext, used_legacy_key = _decrypt(value)
        if not used_legacy_key:
            return value
        value = plaintext
    token = primary.encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def reveal(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        # Legacy local rows remain readable and are encrypted on the next write.
        return value
    plaintext, _used_legacy_key = _decrypt(value)
    return plaintext


def fingerprint(value: str) -> str:
    normalized = "".join(value.split()).upper()
    material = ("wod:sensitive-fingerprint:v1|" + normalized).encode("utf-8")
    # Validate before computing anything that could be persisted. In
    # particular, never generate new fingerprints from SECRET_KEY.
    assert_sensitive_storage_secure()
    key = settings.SENSITIVE_DATA_KEY.strip().encode("ascii")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


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
