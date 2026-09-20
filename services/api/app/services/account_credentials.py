"""Local sign-in credentials for accounts created through KAI identity."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.auth_session import AuthSession
from app.models.external_identity import ExternalIdentity
from app.models.user import User
from app.services.account_lifecycle import ensure_active_user, lock_active_user
from app.services.auth_session import utcnow
from app.utils.response import BizError


KAI_INTERNAL_PHONE_PREFIX = "__kai_"


def internal_kai_phone(issuer: str, subject: str) -> str:
    """Build a stable, non-login placeholder that fits ``users.phone``."""

    digest = hashlib.sha256(f"{issuer}\0{subject}".encode("utf-8")).hexdigest()[:14]
    return f"{KAI_INTERNAL_PHONE_PREFIX}{digest}"


def is_internal_kai_phone(value: str | None) -> bool:
    return str(value or "").startswith(KAI_INTERNAL_PHONE_PREFIX)


def _mask_phone(value: str) -> str:
    if len(value) == 11 and value.isdigit():
        return f"{value[:3]}****{value[-4:]}"
    return ""


def phone_login_status(db: Session, user: User) -> dict[str, object]:
    configured = not is_internal_kai_phone(user.phone)
    has_kai_identity = db.query(ExternalIdentity.id).filter(
        ExternalIdentity.user_id == user.id,
        ExternalIdentity.provider == "kai",
    ).first() is not None
    return {
        "configured": configured,
        "phone_masked": _mask_phone(user.phone) if configured else None,
        "phone_verified": bool(user.phone_bound) if configured else False,
        "can_configure": bool(not configured and has_kai_identity),
        # This deployment intentionally does not claim SMS ownership checks.
        "sms_verification_available": False,
    }


def has_recent_kai_session(
    db: Session,
    user_id: int,
    current_session_id: str | None,
    *,
    for_update: bool = False,
) -> bool:
    """Return whether the current server session is a recent KAI login."""

    if not current_session_id:
        return False
    query = db.query(AuthSession).filter(
        AuthSession.id == current_session_id,
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at >= utcnow(),
        AuthSession.auth_method == "kai_oidc",
        AuthSession.created_at
        >= utcnow() - timedelta(seconds=settings.KAI_AUTH_REAUTH_MAX_AGE_SECONDS),
    ).populate_existing()
    if for_update:
        query = query.with_for_update()
    return query.first() is not None


def configure_initial_phone_login(
    db: Session,
    user: User,
    *,
    phone: str,
    password: str,
    current_session_id: str | None,
) -> User:
    """Set the first local phone/password credential for a KAI-created account.

    The phone remains explicitly unverified until a real SMS ownership flow is
    deployed. This endpoint is not a general phone-change API.
    """

    ensure_active_user(user)
    lock_active_user(db, user.id)
    db.refresh(user)
    if not current_session_id:
        db.rollback()
        raise BizError("请在最近一次 KAI 登录后完成登录手机号设置", status_code=401)
    if not has_recent_kai_session(
        db,
        user.id,
        current_session_id,
        for_update=True,
    ):
        db.rollback()
        raise BizError("请在最近一次 KAI 登录后完成登录手机号设置", status_code=401)
    if not is_internal_kai_phone(user.phone):
        db.rollback()
        raise BizError("登录手机号已设置，如需更换请联系账号服务", status_code=409)
    identity = db.query(ExternalIdentity.id).filter(
        ExternalIdentity.user_id == user.id,
        ExternalIdentity.provider == "kai",
    ).first()
    if not identity:
        db.rollback()
        raise BizError("当前账号未绑定 Kai 身份", status_code=409)
    conflict = db.query(User.id).filter(User.phone == phone, User.id != user.id).first()
    if conflict:
        db.rollback()
        raise BizError("该手机号已存在账号，请使用手机号登录后联系账号服务", status_code=409)

    changed_at = utcnow()
    user.phone = phone
    user.phone_bound = False
    user.password = hash_password(password)
    user.password_set = True
    # Any password/reset proofs issued before the first local credential was
    # configured must not remain usable afterwards.
    from app.services.account_recovery import (
        RESET_PURPOSES,
        VERIFY_EMAIL,
        _expire_open_tokens,
    )

    _expire_open_tokens(db, user.id, (VERIFY_EMAIL, *RESET_PURPOSES), changed_at)
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.id != current_session_id,
        AuthSession.revoked_at.is_(None),
    ).update({AuthSession.revoked_at: changed_at}, synchronize_session=False)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("该手机号已存在账号，请使用手机号登录后联系账号服务", status_code=409) from exc
    db.refresh(user)
    return user
