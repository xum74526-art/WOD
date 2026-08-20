import hashlib
import ipaddress
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Session as LoginSession
from app.models import User

SESSION_COOKIE = "kai_session"
CSRF_COOKIE = "kai_csrf"


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, headers: dict[str, str] | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def digest(value: str) -> str:
    return hashlib.sha256((settings.SECRET_KEY + "|" + value).encode("utf-8")).hexdigest()


def _device_name(user_agent: str) -> str:
    value = user_agent.casefold()
    browser = "Edge" if "edg/" in value else "Chrome" if "chrome/" in value else "Firefox" if "firefox/" in value else "Safari" if "safari/" in value else "API 客户端" if user_agent else "未知客户端"
    system = "iPhone" if "iphone" in value else "iPad" if "ipad" in value else "Android" if "android" in value else "Windows" if "windows" in value else "macOS" if "mac os" in value or "macintosh" in value else "Linux" if "linux" in value else "未知系统"
    return f"{browser} · {system}"


def _masked_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "未知网络"
    if address.version == 4:
        parts = value.split(".")
        return ".".join([*parts[:3], "*"])
    return f"{':'.join(address.exploded.split(':')[:4])}::/64"


def create_session(
    user: User,
    db: Session,
    request: Request,
    *,
    channel: str = "web",
    device_name: str | None = None,
) -> tuple[str, str]:
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    user_agent = request.headers.get("user-agent", "")[:512]
    remote_ip = request.client.host if request.client else ""
    db.add(LoginSession(
        id=uuid.uuid4().hex,
        user_id=user.id,
        channel=channel,
        token_hash=digest(session_token),
        csrf_hash=digest(csrf_token),
        expires_at=now + timedelta(days=settings.SESSION_TTL_DAYS),
        device_name=(device_name or _device_name(user_agent))[:128],
        user_agent=user_agent,
        ip_address_masked=_masked_ip(remote_ip),
        ip_hash=digest(f"session-ip:{remote_ip}") if remote_ip else None,
        last_seen_at=now,
    ))
    db.commit()
    return session_token, csrf_token


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _validate_session(session: LoginSession | None, db: Session) -> LoginSession:
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or _aware(session.expires_at) <= now:
        raise ApiError("SESSION_EXPIRED", "登录状态已过期，请重新登录", 401)
    if session.last_seen_at is None or _aware(session.last_seen_at) <= now - timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return session


def current_session(request: Request, db: Session) -> LoginSession:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise ApiError("AUTH_REQUIRED", "请先登录", 401)
    session = db.query(LoginSession).filter(
        LoginSession.token_hash == digest(token),
        LoginSession.channel == "web",
    ).first()
    return _validate_session(session, db)


def current_bearer_session(authorization: str | None, db: Session) -> LoginSession:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise ApiError("AUTH_REQUIRED", "请先登录", 401, {"WWW-Authenticate": "Bearer"})
    session = db.query(LoginSession).filter(
        LoginSession.token_hash == digest(token),
        LoginSession.channel == "app",
    ).first()
    return _validate_session(session, db)


def _user_for_session(session: LoginSession, db: Session) -> User:
    user = db.query(User).filter(User.id == session.user_id, User.status == "active").first()
    if not user:
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
    return user


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    session = (
        current_bearer_session(authorization, db)
        if authorization
        else current_session(request, db)
    )
    return _user_for_session(session, db)


def get_bearer_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    return _user_for_session(current_bearer_session(authorization, db), db)


def get_optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    if not request.cookies.get(SESSION_COOKIE) and not authorization:
        return None
    try:
        session = current_bearer_session(authorization, db) if authorization else current_session(request, db)
        return _user_for_session(session, db)
    except ApiError:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ApiError("ADMIN_REQUIRED", "仅管理员可以执行此操作", 403)
    return user


def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    session = current_session(request, db)
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    if not cookie_token or not x_csrf_token or not secrets.compare_digest(cookie_token, x_csrf_token):
        raise ApiError("CSRF_INVALID", "页面安全令牌已失效，请刷新后重试", 403)
    if not secrets.compare_digest(session.csrf_hash, digest(x_csrf_token)):
        raise ApiError("CSRF_INVALID", "页面安全令牌已失效，请刷新后重试", 403)
    user = db.query(User).filter(User.id == session.user_id, User.status == "active").first()
    if not user:
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
    return user


def require_authenticated_action(
    request: Request,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate a state-changing request from either supported client channel."""
    if authorization:
        return _user_for_session(current_bearer_session(authorization, db), db)
    session = current_session(request, db)
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    if not cookie_token or not x_csrf_token or not secrets.compare_digest(cookie_token, x_csrf_token):
        raise ApiError("CSRF_INVALID", "页面安全令牌已失效，请刷新后重试", 403)
    if not secrets.compare_digest(session.csrf_hash, digest(x_csrf_token)):
        raise ApiError("CSRF_INVALID", "页面安全令牌已失效，请刷新后重试", 403)
    return _user_for_session(session, db)


def require_admin_csrf(user: User = Depends(require_csrf)) -> User:
    if user.role != "admin":
        raise ApiError("ADMIN_REQUIRED", "仅管理员可以执行此操作", 403)
    return user


def require_admin_action(user: User = Depends(require_authenticated_action)) -> User:
    if user.role != "admin":
        raise ApiError("ADMIN_REQUIRED", "仅管理员可以执行此操作", 403)
    return user


def ensure_verified_email(user: User) -> None:
    if settings.EMAIL_VERIFICATION_ENABLED and not user.email_verified:
        raise ApiError("EMAIL_VERIFICATION_REQUIRED", "请先验证登录邮箱", 403)
