"""Atomic local-account provisioning for a verified KAI identity."""

from __future__ import annotations

import secrets
import string
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.external_identity import ExternalAuthTicket, ExternalIdentity
from app.models.invite import INVITE_CODE_PREFIX, InviteCode
from app.models.user import User
from app.models.wallet import Wallet
from app.services.account_credentials import internal_kai_phone
from app.services.account_lifecycle import lock_active_user
from app.services.auth_session import utcnow
from app.services.kai_auth import find_kai_identity, issuer_url
from app.utils.response import BizError


_INVITE_ALPHABET = string.ascii_uppercase + string.digits
KAI_TERMS_REQUIRED_CODE = 41001


def _optional_text(value: Any, max_length: int) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized[:max_length] or None


def _username(claims: dict[str, Any]) -> str:
    return (
        _optional_text(claims.get("name"), 64)
        or _optional_text(claims.get("preferred_username"), 64)
        or "KAI 用户"
    )


def _new_invite_code(db: Session) -> str:
    for _ in range(12):
        code = INVITE_CODE_PREFIX + "".join(
            secrets.choice(_INVITE_ALPHABET) for _ in range(9)
        )
        if not db.query(InviteCode.id).filter(InviteCode.code == code).first():
            return code
    raise BizError("账号初始化失败，请稍后重试", status_code=503)


def _stage_ticket(
    db: Session,
    user_id: int,
    *,
    platform: str,
    client_id: str | None,
) -> str:
    from datetime import timedelta
    import hashlib

    ticket = secrets.token_urlsafe(32)
    db.add(
        ExternalAuthTicket(
            ticket_hash=hashlib.sha256(ticket.encode("utf-8")).hexdigest(),
            user_id=user_id,
            platform=platform,
            client_id=client_id,
            expires_at=utcnow()
            + timedelta(seconds=settings.KAI_AUTH_TICKET_TTL_SECONDS),
        )
    )
    return ticket


def _apply_claims(identity: ExternalIdentity, user: User, claims: dict[str, Any]) -> None:
    identity.email = _optional_text(claims.get("email"), 320)
    identity.email_verified = claims.get("email_verified") is True
    identity.display_name = _optional_text(claims.get("name"), 128)
    identity.avatar_url = _optional_text(claims.get("picture"), 512)
    if identity.avatar_url and not user.avatar:
        user.avatar = identity.avatar_url


def _existing_user_with_ticket(
    db: Session,
    identity: ExternalIdentity,
    claims: dict[str, Any],
    *,
    platform: str,
    client_id: str | None,
) -> tuple[User, str, bool]:
    user = db.query(User).filter(User.id == identity.user_id).first()
    if not user:
        raise BizError("统一认证关联用户不存在")
    lock_active_user(db, user.id)
    db.refresh(identity)
    _apply_claims(identity, user, claims)
    ticket = _stage_ticket(
        db,
        user.id,
        platform=platform,
        client_id=client_id,
    )
    db.commit()
    db.refresh(user)
    return user, ticket, False


def resolve_or_create_kai_login(
    db: Session,
    claims: dict[str, Any],
    *,
    platform: str,
    client_id: str | None,
    allow_create: bool = False,
    inviter_id: int | None = None,
) -> tuple[User, str, bool]:
    """Return one local user and handoff ticket for a verified KAI subject.

    The external ``issuer + subject`` pair is the only account key. Provider
    email and phone claims are never used to locate or merge local accounts.
    User, identity, wallet, invite code and handoff ticket commit together.
    """

    issuer = issuer_url()
    subject = _optional_text(claims.get("sub"), 255)
    if not issuer or not subject:
        raise BizError("统一认证缺少用户标识")
    for attempt in range(3):
        identity = find_kai_identity(db, subject)
        if identity:
            return _existing_user_with_ticket(
                db,
                identity,
                claims,
                platform=platform,
                client_id=client_id,
            )

        if platform == "admin":
            raise BizError("管理员账号须先由平台绑定统一身份", status_code=403)

        if not allow_create:
            raise BizError(
                "请先同意用户协议和隐私政策",
                code=KAI_TERMS_REQUIRED_CODE,
                status_code=403,
            )

        try:
            user = User(
                username=_username(claims),
                phone=internal_kai_phone(issuer, subject),
                phone_bound=False,
                password=hash_password(secrets.token_urlsafe(48)),
                password_set=False,
                avatar=_optional_text(claims.get("picture"), 512),
                created_platform=platform,
                invited_by=inviter_id,
            )
            db.add(user)
            db.flush()
            identity = ExternalIdentity(
                user_id=user.id,
                provider="kai",
                issuer=issuer,
                subject=subject,
            )
            _apply_claims(identity, user, claims)
            db.add_all(
                [
                    identity,
                    Wallet(
                        user_id=user.id,
                        balance=Decimal("0"),
                        frozen=Decimal("0"),
                    ),
                    InviteCode(
                        user_id=user.id,
                        code=_new_invite_code(db),
                        invited_count=0,
                    ),
                ]
            )
            db.flush()
            if inviter_id is not None:
                inviter = db.query(User).filter(
                    User.id == inviter_id,
                    User.account_status == "active",
                ).first()
                if inviter is None:
                    raise BizError("邀请码无效，请检查后重试")
                from app.routers.invite import create_invite_relationship
                create_invite_relationship(
                    user,
                    inviter_id,
                    db,
                    platform=platform,
                )
            ticket = _stage_ticket(
                db,
                user.id,
                platform=platform,
                client_id=client_id,
            )
            db.commit()
            db.refresh(user)
            return user, ticket, True
        except IntegrityError as exc:
            db.rollback()
            # Concurrent callbacks for the same KAI subject are arbitrated by
            # the unique identity constraint. The loser attaches to the winner
            # and issues its own single-use handoff ticket.
            identity = find_kai_identity(db, subject)
            if identity:
                return _existing_user_with_ticket(
                    db,
                    identity,
                    claims,
                    platform=platform,
                    client_id=client_id,
                )
            if attempt == 2:
                raise BizError("账号初始化冲突，请稍后重试", status_code=409) from exc
        except Exception:
            db.rollback()
            raise

    raise BizError("账号初始化失败，请稍后重试", status_code=503)
