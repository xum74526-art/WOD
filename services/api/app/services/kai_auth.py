"""Kai OAuth 2.1 / OpenID Connect integration.

The browser callback never carries a WOD access token. It carries a short-lived,
single-use handoff ticket which the App exchanges through the API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.external_identity import ExternalAuthFlow, ExternalAuthTicket, ExternalIdentity
from app.models.user import User
from app.models.wallet import Wallet
from app.utils.response import BizError


def _utcnow() -> datetime:
    # Database columns intentionally use naive UTC for SQLite/PostgreSQL parity.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def is_configured() -> bool:
    return all(
        (
            settings.KAI_AUTH_CLIENT_ID.strip(),
            settings.KAI_AUTH_CLIENT_SECRET.strip(),
            settings.KAI_AUTH_CALLBACK_URL.strip(),
            settings.KAI_AUTH_APP_RETURN_URL.strip(),
        )
    )


def public_config() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "issuer": settings.KAI_AUTH_ISSUER.rstrip("/"),
        "scopes": settings.KAI_AUTH_SCOPES.split(),
        "phone_binding_required": True,
    }


def _require_configured() -> None:
    if not is_configured():
        raise BizError("统一认证尚未配置", code=50301, status_code=503)


def _cleanup_expired(db: Session) -> None:
    now = _utcnow()
    db.query(ExternalAuthFlow).filter(ExternalAuthFlow.expires_at < now).delete(synchronize_session=False)
    db.query(ExternalAuthTicket).filter(ExternalAuthTicket.expires_at < now).delete(synchronize_session=False)


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


def create_authorization_flow(db: Session, intent: str, return_url: str | None = None) -> str:
    _require_configured()
    if intent not in {"login", "register"}:
        raise BizError("统一认证请求类型无效")

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
    issuer = settings.KAI_AUTH_ISSUER.rstrip("/")
    return f"{issuer}/oauth2/authorize?{urlencode(params)}"


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
    issuer = settings.KAI_AUTH_ISSUER.rstrip("/")
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
                f"{issuer}/oauth2/token",
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

    issuer = settings.KAI_AUTH_ISSUER.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.KAI_AUTH_HTTP_TIMEOUT) as client:
            response = await client.get(f"{issuer}/jwks", headers={"Accept": "application/json"})
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
    issuer = settings.KAI_AUTH_ISSUER.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.KAI_AUTH_HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{issuer}/oauth2/userinfo",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            info = response.json()
    except (httpx.HTTPError, ValueError):
        return claims
    if info.get("sub") != claims.get("sub"):
        raise BizError("统一认证用户信息不匹配")
    return {**claims, **info}


def find_or_create_user(db: Session, claims: dict[str, Any]) -> User:
    issuer = settings.KAI_AUTH_ISSUER.rstrip("/")
    subject = str(claims["sub"])
    identity = db.query(ExternalIdentity).filter(
        ExternalIdentity.issuer == issuer,
        ExternalIdentity.subject == subject,
    ).first()
    if identity:
        user = db.query(User).filter(User.id == identity.user_id).first()
        if not user:
            raise BizError("统一认证关联用户不存在")
        identity.email = claims.get("email")
        identity.email_verified = bool(claims.get("email_verified"))
        identity.display_name = claims.get("name")
        identity.avatar_url = claims.get("picture")
        if claims.get("picture") and not user.avatar:
            user.avatar = claims["picture"]
        db.commit()
        db.refresh(user)
        return user

    display_name = str(claims.get("name") or "").strip()
    email = str(claims.get("email") or "").strip()
    username = (display_name or (email.split("@", 1)[0] if email else "") or f"Kai用户{subject[-6:]}")[:64]
    internal_phone = "kai_" + hashlib.sha256(f"{issuer}|{subject}".encode("utf-8")).hexdigest()[:16]
    user = User(
        username=username,
        phone=internal_phone,
        phone_bound=False,
        password=hash_password(secrets.token_urlsafe(48)),
        avatar=claims.get("picture"),
        role="personal",
        supplier_status="none",
    )
    db.add(user)
    db.flush()
    db.add(Wallet(user_id=user.id, balance=0, frozen=0))
    db.add(
        ExternalIdentity(
            user_id=user.id,
            provider="kai",
            issuer=issuer,
            subject=subject,
            email=email or None,
            email_verified=bool(claims.get("email_verified")),
            display_name=display_name or None,
            avatar_url=claims.get("picture"),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # A second callback for the same Kai subject may arrive concurrently.
        # The unique issuer+subject constraint decides the winner.
        db.rollback()
        identity = db.query(ExternalIdentity).filter(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        ).first()
        if not identity:
            raise BizError("统一认证账号创建失败")
        existing_user = db.query(User).filter(User.id == identity.user_id).first()
        if not existing_user:
            raise BizError("统一认证关联用户不存在")
        return existing_user
    db.refresh(user)
    # Import lazily to avoid a router/service import cycle.
    from app.routers.auth import _ensure_invite_code

    _ensure_invite_code(user.id, db)
    return user


def issue_handoff_ticket(db: Session, user_id: int) -> str:
    ticket = secrets.token_urlsafe(32)
    db.add(
        ExternalAuthTicket(
            ticket_hash=_sha256(ticket),
            user_id=user_id,
            expires_at=_utcnow() + timedelta(seconds=settings.KAI_AUTH_TICKET_TTL_SECONDS),
        )
    )
    db.commit()
    return ticket


def consume_handoff_ticket(db: Session, ticket: str) -> User:
    if not ticket:
        raise BizError("统一认证登录凭证无效")
    row = db.query(ExternalAuthTicket).filter(ExternalAuthTicket.ticket_hash == _sha256(ticket)).first()
    if not row or row.consumed_at is not None or row.expires_at < _utcnow():
        raise BizError("统一认证登录凭证无效或已过期")
    now = _utcnow()
    updated = db.query(ExternalAuthTicket).filter(
        ExternalAuthTicket.id == row.id,
        ExternalAuthTicket.consumed_at.is_(None),
        ExternalAuthTicket.expires_at >= now,
    ).update({ExternalAuthTicket.consumed_at: now}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise BizError("统一认证登录凭证无效或已过期")
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise BizError("统一认证关联用户不存在")
    db.commit()
    db.refresh(user)
    return user


def append_return_params(return_url: str, **params: str) -> str:
    separator = "&" if "?" in return_url else "?"
    return f"{return_url}{separator}{urlencode(params)}"
