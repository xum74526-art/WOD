from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.core.config import settings
from app.services.auth_session import utcnow
from app.services.account_lifecycle import ensure_active_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session_id: str | None
    platform: str
    client_id: str | None
    auth_method: str


def get_current_auth_context(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    claims = decode_access_token(token)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效或已过期")
    try:
        user_id = int(claims.subject)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 无效或已过期") from None
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    # This must precede the legacy JWT branch, not just session validation.
    ensure_active_user(user)
    if claims.auth_version != int(user.auth_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    db.info["authenticated_user_id"] = user.id
    if not claims.session_id:
        # Signed tokens issued before server-side sessions remain usable during
        # migration, but can only be attributed to the explicit legacy bucket.
        return AuthContext(user, None, "legacy", None, "legacy_token")
    auth_session = db.query(AuthSession).filter(AuthSession.id == claims.session_id).first()
    if (
        not auth_session
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or auth_session.expires_at < utcnow()
        or claims.platform != auth_session.platform
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    return AuthContext(
        user=user,
        session_id=auth_session.id,
        platform=auth_session.platform,
        client_id=auth_session.client_id,
        auth_method=auth_session.auth_method,
    )


def get_current_user(context: AuthContext = Depends(get_current_auth_context)) -> User:
    return context.user


def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Return the signed-in user when present while allowing public reads."""
    if not token:
        return None
    return get_current_auth_context(token, db).user


def get_current_platform(context: AuthContext = Depends(get_current_auth_context)) -> str:
    """Dependency for orders/payments/audit rows that need trusted attribution."""
    return context.platform


def finance_admin_user_ids() -> set[int]:
    """Return the independent finance allow-list, ignoring malformed entries."""
    result: set[int] = set()
    for raw in settings.FINANCE_ADMIN_USER_IDS.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            result.add(value)
    return result


def require_finance_admin(user: User = Depends(get_current_user)) -> User:
    if user.id not in finance_admin_user_ids():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无财务审核权限")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require the platform administrator role for non-finance admin APIs."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无管理员权限")
    return user
