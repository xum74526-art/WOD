import bcrypt
import jwt
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jwt.exceptions import InvalidTokenError

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: str
    session_id: str | None
    platform: str | None
    auth_version: int = 0


def create_access_token(
    subject: str | int,
    expires_minutes: int | None = None,
    *,
    session_id: str | None = None,
    platform: str | None = None,
    auth_version: int = 0,
    expires_at: datetime | None = None,
) -> str:
    expire = expires_at or (
        datetime.now(timezone.utc)
        + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "jti": secrets.token_urlsafe(16),
        "av": int(auth_version),
    }
    if session_id:
        payload["sid"] = session_id
    if platform:
        payload["platform"] = platform
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            return None
        raw_auth_version = payload.get("av", 0)
        if (
            not isinstance(raw_auth_version, int)
            or isinstance(raw_auth_version, bool)
            or raw_auth_version < 0
        ):
            return None
        return AccessTokenClaims(
            subject=str(subject),
            session_id=str(payload["sid"]) if payload.get("sid") else None,
            platform=str(payload["platform"]) if payload.get("platform") else None,
            auth_version=raw_auth_version,
        )
    except InvalidTokenError:
        return None


def decode_token(token: str) -> str | None:
    """Backward-compatible subject decoder for non-request callers."""
    claims = decode_access_token(token)
    return claims.subject if claims else None
