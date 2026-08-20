import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ExternalIdentity, OAuthLoginFlow, OAuthLoginTicket, User
from app.security import ApiError, digest


PROVIDER = "kai"
SCOPES = ("openid", "profile", "email", "phone")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _endpoint(explicit: str, suffix: str) -> str:
    return explicit.strip() or f"{settings.KAI_AUTH_ISSUER.rstrip('/')}/{suffix}"


def authorization_url() -> str:
    return _endpoint(settings.KAI_AUTH_AUTHORIZATION_URL, "authorize")


def token_url() -> str:
    return _endpoint(settings.KAI_AUTH_TOKEN_URL, "token")


def userinfo_url() -> str:
    return _endpoint(settings.KAI_AUTH_USERINFO_URL, "userinfo")


def configured() -> bool:
    return bool(
        settings.KAI_AUTH_ISSUER.strip()
        and settings.KAI_AUTH_CLIENT_ID.strip()
        and settings.KAI_AUTH_CLIENT_SECRET.strip()
        and settings.KAI_AUTH_CALLBACK_URL.strip()
    )


def require_configured() -> None:
    if not configured():
        raise ApiError("KAI_UNCONFIGURED", "Kai 统一认证尚未配置", 503)


def config_out() -> dict:
    return {
        "configured": configured(),
        "issuer": settings.KAI_AUTH_ISSUER,
        "scopes": list(SCOPES),
        "phone_binding_required": False,
    }


def safe_return_to(value: str | None, default: str = "/") -> str:
    candidate = (value or default).strip()
    if not candidate.startswith("/") or candidate.startswith("//") or len(candidate) > 1000:
        return default
    return candidate


def _challenge(verifier: str) -> str:
    raw = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def start_flow(db: Session, *, channel: str, intent: str, return_to: str = "/") -> str:
    require_configured()
    if channel not in {"web", "app"} or intent not in {"login", "register"}:
        raise ApiError("KAI_FLOW_INVALID", "Kai 登录请求无效", 422)
    now = datetime.now(timezone.utc)
    db.query(OAuthLoginFlow).filter(OAuthLoginFlow.expires_at <= now).delete(synchronize_session=False)
    state = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    db.add(OAuthLoginFlow(
        state_hash=digest(f"kai-state:{state}"),
        channel=channel,
        intent=intent,
        return_to=safe_return_to(return_to),
        nonce=nonce,
        code_verifier=verifier,
        expires_at=now + timedelta(minutes=settings.KAI_AUTH_FLOW_TTL_MINUTES),
    ))
    db.commit()
    query = {
        "response_type": "code",
        "client_id": settings.KAI_AUTH_CLIENT_ID,
        "redirect_uri": settings.KAI_AUTH_CALLBACK_URL,
        "scope": " ".join(SCOPES),
        "state": state,
        "nonce": nonce,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
    }
    if intent == "register":
        query["screen_hint"] = "signup"
    return f"{authorization_url()}?{urlencode(query)}"


def consume_flow(db: Session, state: str) -> OAuthLoginFlow:
    if len(state) < 32 or len(state) > 512:
        raise ApiError("KAI_STATE_INVALID", "Kai 登录状态无效或已过期", 400)
    row = db.query(OAuthLoginFlow).filter(
        OAuthLoginFlow.state_hash == digest(f"kai-state:{state}")
    ).with_for_update().first()
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
        raise ApiError("KAI_STATE_INVALID", "Kai 登录状态无效或已过期", 400)
    row.used_at = now
    db.commit()
    return row


def fetch_profile(code: str, flow: OAuthLoginFlow) -> dict:
    if not code or len(code) > 2048:
        raise ApiError("KAI_CODE_INVALID", "Kai 未返回有效授权码", 400)
    timeout = settings.KAI_AUTH_HTTP_TIMEOUT_SECONDS
    try:
        token_response = httpx.post(
            token_url(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.KAI_AUTH_CALLBACK_URL,
                "client_id": settings.KAI_AUTH_CLIENT_ID,
                "client_secret": settings.KAI_AUTH_CLIENT_SECRET,
                "code_verifier": flow.code_verifier,
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise ApiError("KAI_TOKEN_INVALID", "Kai 未返回访问令牌", 502)
        profile_response = httpx.get(
            userinfo_url(),
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=timeout,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    except ApiError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ApiError("KAI_PROVIDER_UNAVAILABLE", "Kai 统一认证暂时不可用", 502) from exc
    if not isinstance(profile, dict):
        raise ApiError("KAI_PROFILE_INVALID", "Kai 身份资料格式无效", 502)
    return profile


def _verified_email(profile: dict) -> str | None:
    value = str(profile.get("email") or "").strip().casefold()
    verified = profile.get("email_verified") in {True, "true", "1", 1}
    if not verified or len(value) > 255 or value.startswith("@") or value.endswith("@") or "@" not in value:
        return None
    return value


def _verified_phone(profile: dict) -> str | None:
    value = re.sub(r"[\s()-]", "", str(profile.get("phone_number") or profile.get("phone") or ""))
    verified = profile.get("phone_number_verified") in {True, "true", "1", 1}
    if not verified or not re.fullmatch(r"\+?[0-9]{6,20}", value):
        return None
    return value


def _display_name(profile: dict) -> str:
    name = str(profile.get("name") or profile.get("preferred_username") or "Kai 用户").strip()
    return name[:64] if len(name) >= 2 else "Kai 用户"


def resolve_user(db: Session, flow: OAuthLoginFlow, profile: dict) -> User:
    subject = str(profile.get("sub") or "").strip()
    issuer = str(profile.get("iss") or settings.KAI_AUTH_ISSUER).strip().rstrip("/")
    expected_issuer = settings.KAI_AUTH_ISSUER.strip().rstrip("/")
    if not subject or len(subject) > 255:
        raise ApiError("KAI_PROFILE_INVALID", "Kai 身份资料缺少用户标识", 502)
    if issuer != expected_issuer:
        raise ApiError("KAI_ISSUER_INVALID", "Kai 身份签发方无效", 400)

    identity = db.query(ExternalIdentity).filter(
        ExternalIdentity.provider == PROVIDER,
        ExternalIdentity.issuer == expected_issuer,
        ExternalIdentity.subject == subject,
    ).first()
    email = _verified_email(profile)
    phone = _verified_phone(profile)
    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None or user.status != "active":
            raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
        identity.email = email
        identity.phone = phone
        if email and (not user.email or user.email == email):
            user.email = email
            user.email_verified = True
        if phone and (not user.phone or user.phone == phone):
            user.phone = phone
            user.phone_verified = True
        db.commit()
        return user

    email_user = db.query(User).filter(User.email == email).first() if email else None
    phone_user = db.query(User).filter(User.phone == phone).first() if phone else None
    if email_user is not None and phone_user is not None and email_user.id != phone_user.id:
        raise ApiError("KAI_IDENTITY_CONFLICT", "Kai 返回的邮箱和手机号属于不同账号，请联系支持", 409)
    user = email_user or phone_user
    if user is None:
        if flow.intent == "login":
            raise ApiError("KAI_ACCOUNT_NOT_FOUND", "该 Kai 身份尚未注册，请先选择注册", 404)
        user = User(
            display_name=_display_name(profile),
            email=email,
            email_verified=bool(email),
            phone=phone,
            phone_verified=bool(phone),
            password_hash=None,
            role="personal",
            status="active",
        )
        db.add(user)
        db.flush()
    elif user.status != "active":
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)

    existing_provider = db.query(ExternalIdentity).filter(
        ExternalIdentity.user_id == user.id,
        ExternalIdentity.provider == PROVIDER,
    ).first()
    if existing_provider is not None:
        raise ApiError("KAI_IDENTITY_CONFLICT", "该账号已经绑定另一个 Kai 身份", 409)
    if email:
        user.email = email
        user.email_verified = True
    if phone:
        user.phone = phone
        user.phone_verified = True
    db.add(ExternalIdentity(
        user_id=user.id,
        provider=PROVIDER,
        issuer=expected_issuer,
        subject=subject,
        email=email,
        phone=phone,
    ))
    db.commit()
    db.refresh(user)
    return user


def issue_app_ticket(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    db.query(OAuthLoginTicket).filter(OAuthLoginTicket.expires_at <= now).delete(synchronize_session=False)
    raw = secrets.token_urlsafe(48)
    db.add(OAuthLoginTicket(
        token_hash=digest(f"kai-ticket:{raw}"),
        user_id=user.id,
        expires_at=now + timedelta(minutes=settings.KAI_AUTH_TICKET_TTL_MINUTES),
    ))
    db.commit()
    return raw


def consume_app_ticket(db: Session, ticket: str) -> User:
    if len(ticket) < 16 or len(ticket) > 512:
        raise ApiError("KAI_TICKET_INVALID", "Kai 登录凭证无效或已过期", 400)
    row = db.query(OAuthLoginTicket).filter(
        OAuthLoginTicket.token_hash == digest(f"kai-ticket:{ticket}")
    ).with_for_update().first()
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
        raise ApiError("KAI_TICKET_INVALID", "Kai 登录凭证无效或已过期", 400)
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
    row.used_at = now
    db.commit()
    return user
