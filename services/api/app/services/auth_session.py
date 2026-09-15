from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.auth_session import AuthSession
from app.models.user import User
from app.utils.response import BizError
from app.services.account_lifecycle import ensure_active_user, lock_active_user


PLATFORMS = frozenset({"web", "ios", "android", "admin", "system", "legacy"})
# Public admin filters intentionally omit ``system``: it describes background
# mutations, not a user-facing client that originated an account/order.
AuditPlatform = Literal["web", "ios", "android", "admin", "legacy"]
AUDIT_PLATFORMS: tuple[AuditPlatform, ...] = (
    "web", "ios", "android", "admin", "legacy",
)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: AuthSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def registered_clients() -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in settings.AUTH_CLIENT_PLATFORM_MAP.split(","):
        client_id, separator, platform = entry.strip().partition("=")
        client_id = client_id.strip()
        platform = platform.strip().lower()
        if not separator or not client_id or platform not in PLATFORMS - {"system", "legacy"}:
            continue
        result[client_id] = platform
    return result


def normalize_platform(value: object, *, fallback: str = "legacy") -> str:
    """Normalize injected values while keeping direct service tests legacy-safe."""
    return value if isinstance(value, str) and value in PLATFORMS else fallback


def resolve_client(
    client_id: str | None,
    user: User | None = None,
    *,
    allow_admin_before_identity: bool = False,
) -> tuple[str, str | None]:
    """Resolve a stable registered client; never accept a raw platform label."""
    normalized = str(client_id or "").strip()
    if not normalized:
        return "legacy", None
    platform = registered_clients().get(normalized)
    if not platform:
        raise BizError("客户端标识未注册", status_code=400)
    if platform == "admin" and user is None and not allow_admin_before_identity:
        raise BizError("管理员客户端仅允许管理员账号使用", status_code=403)
    if platform == "admin" and user is not None and user.role != "admin":
        raise BizError("管理员客户端仅允许管理员账号使用", status_code=403)
    return platform, normalized


def create_authenticated_session(
    db: Session,
    user: User,
    *,
    platform: str,
    client_id: str | None,
    auth_method: str,
) -> IssuedSession:
    ensure_active_user(user)
    lock_active_user(db, user.id)
    if platform not in PLATFORMS - {"system"}:
        raise BizError("会话来源无效")
    if platform == "admin" and user.role != "admin":
        raise BizError("管理员客户端仅允许管理员账号使用", status_code=403)
    expires_at = utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    row = AuthSession(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        platform=platform,
        client_id=client_id,
        auth_method=auth_method,
        expires_at=expires_at,
    )
    db.add(row)
    token_expiry = expires_at.replace(tzinfo=timezone.utc)
    token = create_access_token(
        user.id,
        session_id=row.id,
        platform=row.platform,
        auth_version=int(user.auth_version or 0),
        expires_at=token_expiry,
    )
    # Generate the bearer before committing. If signing/configuration fails,
    # callers can roll the pending AuthSession back with the rest of their
    # transaction instead of persisting a session they can never return.
    db.commit()
    return IssuedSession(token=token, session=row)


def revoke_current_session(
    db: Session,
    *,
    user_id: int,
    session_id: str | None,
) -> bool:
    """Revoke only the server-owned session identified by the signed token."""
    if not session_id:
        # Legacy JWTs have no server-owned session that can be revoked without
        # also invalidating every device through the user's auth version.
        raise BizError("当前会话不支持单独退出，请重新登录", status_code=401)
    revoked = db.query(AuthSession).filter(
        AuthSession.id == session_id,
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ).update(
        {AuthSession.revoked_at: utcnow()},
        synchronize_session=False,
    )
    # A concurrent retry may already have revoked the row. Committing an
    # unchanged transaction keeps logout idempotent at the mutation boundary.
    db.commit()
    return bool(revoked)
