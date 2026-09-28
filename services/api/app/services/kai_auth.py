"""Kai OAuth 2.1 / OpenID Connect integration.

The browser callback never carries a ZTW access token. It carries a short-lived,
single-use handoff ticket which the App exchanges through the API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.external_identity import (
    ExternalAuthBindTicket,
    ExternalAuthFlow,
    ExternalAuthTicket,
    ExternalIdentity,
)
from app.models.user import User
from app.utils.response import BizError


def _utcnow() -> datetime:
    # Database columns intentionally use naive UTC for SQLite/PostgreSQL parity.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


_KAI_ENDPOINT_PATH = "/api/auth"


def issuer_url() -> str:
    """Return the canonical OIDC issuer used in signed responses and tokens.

    Older deployments stored the KAI endpoint base in ``KAI_AUTH_ISSUER``.
    Normalising that legacy value keeps a rolling deployment usable while the
    private environment is updated to the standards-compliant split config.
    """

    configured = settings.KAI_AUTH_ISSUER.strip().rstrip("/")
    if configured.endswith(_KAI_ENDPOINT_PATH):
        return configured[: -len(_KAI_ENDPOINT_PATH)]
    return configured


def endpoint_base_url() -> str:
    """Return the base URL that hosts KAI's OAuth and OIDC endpoints."""

    explicit = settings.KAI_AUTH_ENDPOINT_BASE.strip().rstrip("/")
    if explicit:
        return explicit
    configured = settings.KAI_AUTH_ISSUER.strip().rstrip("/")
    if configured.endswith(_KAI_ENDPOINT_PATH):
        return configured
    return f"{configured}{_KAI_ENDPOINT_PATH}" if configured else ""


def identity_issuer_urls() -> tuple[str, ...]:
    """Return canonical and historically persisted KAI issuer values.

    Earlier releases used the OAuth endpoint base as the identity issuer.  A
    rolling deployment must still locate those rows, then rewrite them to the
    issuer declared by KAI's OpenID metadata.
    """

    values = (
        issuer_url(),
        settings.KAI_AUTH_ISSUER.strip().rstrip("/"),
        endpoint_base_url(),
    )
    return tuple(dict.fromkeys(value for value in values if value))


def find_kai_identity(db: Session, subject: str) -> ExternalIdentity | None:
    """Find one KAI subject across issuer aliases and normalize it in-place."""

    identities = db.query(ExternalIdentity).filter(
        ExternalIdentity.provider == "kai",
        ExternalIdentity.issuer.in_(identity_issuer_urls()),
        ExternalIdentity.subject == subject,
    ).all()
    if len(identities) > 1:
        raise BizError(
            "统一认证身份存在历史冲突，请联系平台处理",
            status_code=409,
        )
    if not identities:
        return None
    identity = identities[0]
    canonical = issuer_url()
    if identity.issuer != canonical:
        identity.issuer = canonical
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise BizError(
                "统一认证身份存在历史冲突，请联系平台处理",
                status_code=409,
            ) from exc
    return identity


def is_configured() -> bool:
    return all(
        (
            issuer_url(),
            endpoint_base_url(),
            settings.KAI_AUTH_CLIENT_ID.strip(),
            settings.KAI_AUTH_CLIENT_SECRET.strip(),
            settings.KAI_AUTH_CALLBACK_URL.strip(),
            settings.KAI_AUTH_APP_RETURN_URL.strip(),
        )
    )


def public_config() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "issuer": issuer_url(),
        "scopes": settings.KAI_AUTH_SCOPES.split(),
        "auto_provision_enabled": True,
        "phone_binding_required": False,
        "phone_login_setup_enabled": True,
        "sms_verification_available": False,
    }


def _require_configured() -> None:
    if not is_configured():
        raise BizError("统一认证尚未配置", code=50301, status_code=503)


def _cleanup_expired(db: Session) -> None:
    now = _utcnow()
    db.query(ExternalAuthFlow).filter(ExternalAuthFlow.expires_at < now).delete(synchronize_session=False)
    db.query(ExternalAuthTicket).filter(ExternalAuthTicket.expires_at < now).delete(synchronize_session=False)
    db.query(ExternalAuthBindTicket).filter(
        ExternalAuthBindTicket.expires_at < now
    ).delete(synchronize_session=False)


def _return_url(requested: str | None) -> str:
    default = settings.KAI_AUTH_APP_RETURN_URL.strip()
    allowed = {
        value.strip()
        for value in (default, *settings.KAI_AUTH_ALLOWED_RETURN_URLS.split(","))
        if value.strip()
    }
    candidate = (requested or default).strip()
    if candidate not in allowed:
        raise BizError("统一认证返回地址无效")
    return candidate


def create_authorization_flow(
    db: Session,
    intent: str,
    return_url: str | None = None,
    *,
    user_id: int | None = None,
    inviter_id: int | None = None,
    platform: str = "legacy",
    client_id: str | None = None,
    terms_accepted: bool = False,
) -> str:
    _require_configured()
    if intent not in {"login", "register", "bind", "recover", "delete"}:
        raise BizError("统一认证请求类型无效")
    authenticated_intents = {"bind", "delete"}
    if intent in authenticated_intents and not user_id:
        raise BizError("此统一认证操作必须先登录", status_code=401)
    if intent not in authenticated_intents and user_id is not None:
        raise BizError("统一认证流程目标用户无效")
    if inviter_id is not None and intent != "register":
        raise BizError("邀请码仅适用于新账号注册")

    _cleanup_expired(db)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    db.add(
        ExternalAuthFlow(
            state_hash=_sha256(state),
            code_verifier=code_verifier,
            nonce=nonce,
            intent=intent,
            terms_accepted=bool(terms_accepted),
            user_id=user_id,
            inviter_id=inviter_id,
            platform=platform,
            client_id=client_id,
            return_url=_return_url(return_url),
            expires_at=_utcnow() + timedelta(seconds=settings.KAI_AUTH_FLOW_TTL_SECONDS),
        )
    )
    db.commit()

    params = {
        "client_id": settings.KAI_AUTH_CLIENT_ID,
        "redirect_uri": settings.KAI_AUTH_CALLBACK_URL,
        "response_type": "code",
        "response_mode": "query",
        "scope": settings.KAI_AUTH_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if intent == "register":
        params["prompt"] = "create"
    elif intent in {"recover", "delete"}:
        # Recovery and deletion must be fresh identity checks, not silent reuse
        # of an old provider session.
        params["prompt"] = "login"
        params["max_age"] = "0"
    return f"{endpoint_base_url()}/oauth2/authorize?{urlencode(params)}"


def get_flow(db: Session, state: str) -> ExternalAuthFlow:
    if not state:
        raise BizError("统一认证状态无效")
    flow = db.query(ExternalAuthFlow).filter(ExternalAuthFlow.state_hash == _sha256(state)).first()
    if not flow or flow.consumed_at is not None or flow.expires_at < _utcnow():
        raise BizError("统一认证状态无效或已过期")
    return flow


def consume_flow(db: Session, flow: ExternalAuthFlow) -> None:
    now = _utcnow()
    updated = db.query(ExternalAuthFlow).filter(
        ExternalAuthFlow.id == flow.id,
        ExternalAuthFlow.consumed_at.is_(None),
        ExternalAuthFlow.expires_at >= now,
    ).update({ExternalAuthFlow.consumed_at: now}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise BizError("统一认证状态无效或已过期")
    db.commit()


async def exchange_authorization_code(code: str, flow: ExternalAuthFlow) -> dict[str, Any]:
    _require_configured()
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.KAI_AUTH_CALLBACK_URL,
        "client_id": settings.KAI_AUTH_CLIENT_ID,
        "code_verifier": flow.code_verifier,
    }
    timeout = settings.KAI_AUTH_HTTP_TIMEOUT
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{endpoint_base_url()}/oauth2/token",
                data=payload,
                auth=(settings.KAI_AUTH_CLIENT_ID, settings.KAI_AUTH_CLIENT_SECRET),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BizError("统一认证授权码交换失败") from exc
    if not token_data.get("id_token"):
        raise BizError("统一认证未返回身份令牌")
    return token_data


async def verify_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    parts = id_token.split(".")
    if len(parts) != 3:
        raise BizError("统一认证身份令牌格式无效")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except (ValueError, json.JSONDecodeError) as exc:
        raise BizError("统一认证身份令牌格式无效") from exc
    if header.get("alg") != "EdDSA" or not header.get("kid"):
        raise BizError("统一认证身份令牌签名算法无效")

    issuer = issuer_url()
    try:
        async with httpx.AsyncClient(timeout=settings.KAI_AUTH_HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{endpoint_base_url()}/jwks",
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            keys = response.json().get("keys", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise BizError("统一认证签名密钥获取失败") from exc
    jwk = next((key for key in keys if key.get("kid") == header["kid"]), None)
    if not jwk or jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519" or not jwk.get("x"):
        raise BizError("统一认证签名密钥无效")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))
        public_key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"))
    except Exception as exc:
        raise BizError("统一认证身份令牌签名无效") from exc

    now = int(datetime.now(timezone.utc).timestamp())
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if claims.get("iss") != issuer:
        raise BizError("统一认证签发方无效")
    if settings.KAI_AUTH_CLIENT_ID not in audiences:
        raise BizError("统一认证身份令牌受众无效")
    if len(audiences) > 1 and claims.get("azp") != settings.KAI_AUTH_CLIENT_ID:
        raise BizError("统一认证授权方无效")
    if not isinstance(claims.get("exp"), int) or claims["exp"] <= now:
        raise BizError("统一认证身份令牌已过期")
    if isinstance(claims.get("iat"), int) and claims["iat"] > now + 60:
        raise BizError("统一认证身份令牌签发时间无效")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise BizError("统一认证随机校验失败")
    if not claims.get("sub"):
        raise BizError("统一认证缺少用户标识")
    return claims


async def enrich_with_userinfo(claims: dict[str, Any], access_token: str | None) -> dict[str, Any]:
    if not access_token:
        return claims
    try:
        async with httpx.AsyncClient(timeout=settings.KAI_AUTH_HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{endpoint_base_url()}/oauth2/userinfo",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            info = response.json()
    except (httpx.HTTPError, ValueError):
        return claims
    if info.get("sub") != claims.get("sub"):
        raise BizError("统一认证用户信息不匹配")
    return {**claims, **info}


def find_bound_user(
    db: Session,
    claims: dict[str, Any],
    *,
    expected_user_id: int | None = None,
) -> User | None:
    """Find an explicitly bound local user; never create a ZTW account."""
    subject = str(claims["sub"])
    identity = find_kai_identity(db, subject)
    if not identity:
        return None
    if expected_user_id is not None and identity.user_id != expected_user_id:
        raise BizError("统一认证身份与当前账号不匹配")
    user = db.query(User).filter(User.id == identity.user_id).first()
    if not user:
        raise BizError("统一认证关联用户不存在")
    from app.services.account_lifecycle import lock_active_user
    lock_active_user(db, user.id)
    identity.email = _optional_text(claims.get("email"), 320)
    identity.email_verified = claims.get("email_verified") is True
    identity.display_name = _optional_text(claims.get("name"), 128)
    identity.avatar_url = _optional_text(claims.get("picture"), 512)
    if identity.avatar_url and not user.avatar:
        user.avatar = identity.avatar_url
    db.commit()
    db.refresh(user)
    return user


def issue_handoff_ticket(
    db: Session,
    user_id: int,
    *,
    platform: str = "legacy",
    client_id: str | None = None,
) -> str:
    from app.services.account_lifecycle import lock_active_user
    lock_active_user(db, user_id)
    ticket = secrets.token_urlsafe(32)
    db.add(
        ExternalAuthTicket(
            ticket_hash=_sha256(ticket),
            user_id=user_id,
            platform=platform,
            client_id=client_id,
            expires_at=_utcnow() + timedelta(seconds=settings.KAI_AUTH_TICKET_TTL_SECONDS),
        )
    )
    db.commit()
    return ticket


def consume_handoff_ticket(
    db: Session,
    ticket: str,
    *,
    commit: bool = True,
) -> tuple[User, str, str | None]:
    """Consume a single-use ticket, optionally leaving commit to the caller."""
    if not ticket:
        raise BizError("统一认证登录凭证无效")
    ticket_hash = _sha256(ticket)
    now = _utcnow()
    updated = db.query(ExternalAuthTicket).filter(
        ExternalAuthTicket.ticket_hash == ticket_hash,
        ExternalAuthTicket.consumed_at.is_(None),
        ExternalAuthTicket.expires_at >= now,
    ).update({ExternalAuthTicket.consumed_at: now}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise BizError("统一认证登录凭证无效或已过期")
    # Claim first, then load the immutable ticket metadata. Starting with the
    # conditional UPDATE lets SQLite serialize concurrent redeemers without a
    # read-to-write upgrade window; PostgreSQL keeps the same row-lock semantics.
    row = db.query(ExternalAuthTicket).filter(
        ExternalAuthTicket.ticket_hash == ticket_hash,
    ).one()
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise BizError("统一认证关联用户不存在")
    if commit:
        db.commit()
    # Keep the returned account fresh even when the caller owns the final
    # commit; auth_version and lifecycle state feed the session token.
    db.refresh(user)
    return user, row.platform or "legacy", row.client_id


def _optional_text(value: Any, max_length: int) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:max_length] or None


def issue_bind_ticket(
    db: Session,
    user_id: int,
    claims: dict[str, Any],
    *,
    platform: str,
    client_id: str | None,
) -> str:
    from app.services.account_lifecycle import lock_active_user
    lock_active_user(db, user_id)
    subject = _optional_text(claims.get("sub"), 255)
    if not subject:
        raise BizError("统一认证缺少用户标识")
    ticket = secrets.token_urlsafe(32)
    db.add(
        ExternalAuthBindTicket(
            ticket_hash=_sha256(ticket),
            user_id=user_id,
            provider="kai",
            issuer=issuer_url(),
            subject=subject,
            email=_optional_text(claims.get("email"), 320),
            email_verified=claims.get("email_verified") is True,
            display_name=_optional_text(claims.get("name"), 128),
            avatar_url=_optional_text(claims.get("picture"), 512),
            platform=platform,
            client_id=client_id,
            expires_at=_utcnow() + timedelta(seconds=settings.KAI_AUTH_TICKET_TTL_SECONDS),
        )
    )
    db.commit()
    return ticket


def bind_identity_with_ticket(db: Session, ticket: str, user: User) -> ExternalIdentity:
    """Atomically consume a verified ticket and bind it to its initiating user."""
    if not ticket:
        raise BizError("统一认证绑定凭证无效")
    from app.services.account_lifecycle import lock_active_user
    lock_active_user(db, user.id)
    now = _utcnow()
    row = db.query(ExternalAuthBindTicket).filter(
        ExternalAuthBindTicket.ticket_hash == _sha256(ticket)
    ).first()
    if (
        not row
        or row.user_id != user.id
        or row.consumed_at is not None
        or row.expires_at < now
    ):
        raise BizError("统一认证绑定凭证无效或已过期")

    is_kai_identity = row.provider == "kai" and row.issuer in identity_issuer_urls()
    row_issuer = issuer_url() if is_kai_identity else row.issuer
    subject_identity = (
        find_kai_identity(db, row.subject)
        if is_kai_identity
        else db.query(ExternalIdentity).filter(
            ExternalIdentity.provider == row.provider,
            ExternalIdentity.issuer == row_issuer,
            ExternalIdentity.subject == row.subject,
        ).first()
    )
    user_identity = db.query(ExternalIdentity).filter(
        ExternalIdentity.user_id == user.id,
        ExternalIdentity.provider == row.provider,
    ).first()
    if subject_identity and subject_identity.user_id != user.id:
        raise BizError("该 Kai 身份已绑定其他账号", status_code=409)
    user_issuer_matches = bool(
        user_identity
        and (
            user_identity.issuer in identity_issuer_urls()
            if is_kai_identity
            else user_identity.issuer == row_issuer
        )
    )
    if user_identity and (
        not user_issuer_matches or user_identity.subject != row.subject
    ):
        raise BizError("当前账号已绑定其他 Kai 身份", status_code=409)

    identity = subject_identity or user_identity
    if not identity:
        identity = ExternalIdentity(
            user_id=user.id,
            provider=row.provider,
            issuer=row_issuer,
            subject=row.subject,
        )
        db.add(identity)
    elif identity.issuer != row_issuer:
        identity.issuer = row_issuer
    identity.email = row.email
    identity.email_verified = row.email_verified
    identity.display_name = row.display_name
    identity.avatar_url = row.avatar_url
    if row.avatar_url and not user.avatar:
        user.avatar = row.avatar_url
    consumed = db.query(ExternalAuthBindTicket).filter(
        ExternalAuthBindTicket.id == row.id,
        ExternalAuthBindTicket.consumed_at.is_(None),
        ExternalAuthBindTicket.expires_at >= now,
    ).update({ExternalAuthBindTicket.consumed_at: now}, synchronize_session=False)
    if consumed != 1:
        db.rollback()
        raise BizError("统一认证绑定凭证无效或已过期")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("Kai 身份绑定冲突", status_code=409) from exc
    db.refresh(identity)
    return identity


def append_return_params(return_url: str, **params: str) -> str:
    separator = "&" if "?" in return_url else "?"
    return f"{return_url}{separator}{urlencode(params)}"


def append_return_fragment(return_url: str, **params: str) -> str:
    """Put recovery secrets in the browser fragment, never the HTTP query."""

    parsed = urlsplit(return_url)
    fragment = dict(parse_qsl(parsed.fragment, keep_blank_values=True))
    fragment.update(params)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, urlencode(fragment)))
