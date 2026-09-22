"""Account recovery rules shared by email and freshly verified KAI identity."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.sensitive import fingerprint, protect, reveal
from app.integrations.account_email import require_email_delivery
from app.models.account_recovery import AccountRecoveryToken
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.account_lifecycle import ensure_active_user, lock_active_user
from app.services.account_recovery_mail import (
    enqueue_password_changed_notice,
    enqueue_recovery_email,
    enqueue_suppressed_password_reset,
)
from app.services.auth_session import utcnow
from app.services.account_credentials import has_recent_kai_session
from app.utils.email_address import normalize_email
from app.utils.response import BizError


VERIFY_EMAIL = "verify_email"
PASSWORD_RESET_EMAIL = "password_reset_email"
PASSWORD_RESET_KAI = "password_reset_kai"
RESET_PURPOSES = (PASSWORD_RESET_EMAIL, PASSWORD_RESET_KAI)
INVALID_TOKEN_MESSAGE = "链接无效或已过期，请重新申请"
INVALID_SESSION_MESSAGE = "会话无效或已过期"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _expire_open_tokens(db: Session, user_id: int, purposes: tuple[str, ...], now=None) -> None:
    consumed_at = now or utcnow()
    db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.user_id == user_id,
        AccountRecoveryToken.purpose.in_(purposes),
        AccountRecoveryToken.consumed_at.is_(None),
    ).update(
        {
            AccountRecoveryToken.consumed_at: consumed_at,
            AccountRecoveryToken.target_email: None,
            AccountRecoveryToken.target_email_fingerprint: None,
        },
        synchronize_session=False,
    )


def _refresh_locked_user(
    db: Session,
    user: User,
    *,
    expected_auth_version: int | None = None,
    current_session_id: str | None = None,
) -> User:
    """Reload authorization state only after the account write fence is held."""

    lock_active_user(db, user.id)
    db.refresh(user)
    ensure_active_user(user)
    if (
        expected_auth_version is not None
        and int(user.auth_version or 0) != expected_auth_version
    ):
        db.rollback()
        raise BizError(INVALID_SESSION_MESSAGE, status_code=401)
    if current_session_id:
        session = db.query(AuthSession).filter(
            AuthSession.id == current_session_id,
            AuthSession.user_id == user.id,
        ).populate_existing().with_for_update().first()
        if (
            not session
            or session.revoked_at is not None
            or session.expires_at < utcnow()
        ):
            db.rollback()
            raise BizError(INVALID_SESSION_MESSAGE, status_code=401)
    return user


def recovery_email_status(
    user: User,
    db: Session | None = None,
    current_session_id: str | None = None,
) -> dict[str, object]:
    plain = reveal(user.recovery_email)
    verified = bool(plain and user.recovery_email_verified_at)
    kai_reauth_available = bool(
        not user.password_set
        and db is not None
        and has_recent_kai_session(db, user.id, current_session_id)
    )
    return {
        "email": plain if verified else None,
        "verified": verified,
        "current_password_required": bool(user.password_set),
        "kai_reauth_available": kai_reauth_available,
        "kai_reauth_required": bool(not user.password_set and not kai_reauth_available),
    }


def request_email_verification(
    db: Session,
    user: User,
    email: str,
    current_password: str | None,
    current_session_id: str | None = None,
) -> tuple[bool, str | None, str]:
    require_email_delivery()
    ensure_active_user(user)
    expected_auth_version = int(user.auth_version or 0)
    normalized = normalize_email(email)
    email_fingerprint = fingerprint(normalized)
    _refresh_locked_user(
        db,
        user,
        expected_auth_version=expected_auth_version,
        current_session_id=current_session_id,
    )
    if current_password:
        if not verify_password(current_password, user.password):
            db.rollback()
            raise BizError("当前密码错误")
    elif user.password_set:
        db.rollback()
        raise BizError("请输入当前密码")
    elif not has_recent_kai_session(db, user.id, current_session_id):
        db.rollback()
        raise BizError("请使用 Kai 重新登录后绑定邮箱", status_code=401)
    conflict = db.query(User.id).filter(
        User.recovery_email_fingerprint == email_fingerprint,
        User.id != user.id,
    ).first()
    if conflict:
        db.rollback()
        # Do not give an authenticated account a directory of other users'
        # recovery addresses. The HTTP response stays identical to a normal
        # verification request, but no token or email is issued.
        return False, None, normalized
    if (
        user.recovery_email_fingerprint == email_fingerprint
        and user.recovery_email_verified_at is not None
    ):
        db.rollback()
        return True, None, normalized

    now = utcnow()
    _expire_open_tokens(db, user.id, (VERIFY_EMAIL,), now)
    token = _new_token()
    token_row = AccountRecoveryToken(
        user_id=user.id,
        purpose=VERIFY_EMAIL,
        token_hash=_token_hash(token),
        target_email=protect(normalized),
        target_email_fingerprint=email_fingerprint,
        auth_version_snapshot=user.auth_version,
        expires_at=now + timedelta(seconds=settings.ACCOUNT_RECOVERY_VERIFY_TTL_SECONDS),
    )
    db.add(token_row)
    enqueue_recovery_email(
        db,
        kind=VERIFY_EMAIL,
        recipient=normalized,
        token=token,
        token_row=token_row,
        expires_at=token_row.expires_at,
    )
    db.commit()
    return False, token, normalized


def confirm_recovery_email(db: Session, token: str) -> User:
    now = utcnow()
    row = db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.token_hash == _token_hash(token),
        AccountRecoveryToken.purpose == VERIFY_EMAIL,
        AccountRecoveryToken.consumed_at.is_(None),
        AccountRecoveryToken.expires_at >= now,
    ).first()
    if not row or not row.target_email or not row.target_email_fingerprint:
        raise BizError(INVALID_TOKEN_MESSAGE)
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise BizError(INVALID_TOKEN_MESSAGE)
    lock_active_user(db, user.id)
    db.refresh(user)
    db.refresh(row)
    ensure_active_user(user)
    now = utcnow()
    if (
        row.consumed_at is not None
        or row.expires_at < now
        or not row.target_email
        or not row.target_email_fingerprint
        or row.auth_version_snapshot != int(user.auth_version or 0)
    ):
        db.rollback()
        raise BizError(INVALID_TOKEN_MESSAGE)
    conflict = db.query(User.id).filter(
        User.recovery_email_fingerprint == row.target_email_fingerprint,
        User.id != user.id,
    ).first()
    if conflict:
        db.rollback()
        raise BizError("该邮箱已被其他账号使用")
    updated = db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.id == row.id,
        AccountRecoveryToken.consumed_at.is_(None),
        AccountRecoveryToken.expires_at >= now,
    ).update({AccountRecoveryToken.consumed_at: now}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise BizError(INVALID_TOKEN_MESSAGE)
    user.recovery_email = row.target_email
    user.recovery_email_fingerprint = row.target_email_fingerprint
    user.recovery_email_verified_at = now
    # A reset proof sent to the previously verified mailbox must not survive
    # replacing that mailbox.
    _expire_open_tokens(db, user.id, (VERIFY_EMAIL, *RESET_PURPOSES), now)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise BizError("该邮箱已被其他账号使用") from error
    db.refresh(user)
    return user


def request_password_reset(db: Session, email: str) -> tuple[str, str] | None:
    """Issue a token only for a verified active address; callers stay generic."""

    require_email_delivery()
    normalized = normalize_email(email)
    email_fingerprint = fingerprint(normalized)
    user = db.query(User).filter(
        User.recovery_email_fingerprint == email_fingerprint,
        User.recovery_email_verified_at.is_not(None),
        User.account_status == "active",
    ).first()
    if not user:
        now = utcnow()
        enqueue_suppressed_password_reset(
            db,
            recipient=normalized,
            expires_at=now + timedelta(
                seconds=settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS
            ),
        )
        db.commit()
        return None
    expected_auth_version = int(user.auth_version or 0)
    try:
        lock_active_user(db, user.id)
    except BizError:
        db.rollback()
        now = utcnow()
        enqueue_suppressed_password_reset(
            db,
            recipient=normalized,
            expires_at=now + timedelta(
                seconds=settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS
            ),
        )
        db.commit()
        return None
    db.refresh(user)
    stored_email = reveal(user.recovery_email)
    if (
        user.account_status != "active"
        or int(user.auth_version or 0) != expected_auth_version
        or user.recovery_email_verified_at is None
        or user.recovery_email_fingerprint != email_fingerprint
        or stored_email != normalized
    ):
        db.rollback()
        now = utcnow()
        enqueue_suppressed_password_reset(
            db,
            recipient=normalized,
            expires_at=now + timedelta(
                seconds=settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS
            ),
        )
        db.commit()
        return None
    token = _queue_password_reset_for_user(db, user, stored_email)
    db.commit()
    return token, stored_email


def _queue_password_reset_for_user(db: Session, user: User, stored_email: str) -> str:
    """Queue a reset proof inside the caller's current transaction."""

    now = utcnow()
    _expire_open_tokens(db, user.id, (PASSWORD_RESET_EMAIL,), now)
    token = _new_token()
    token_row = AccountRecoveryToken(
        user_id=user.id,
        purpose=PASSWORD_RESET_EMAIL,
        token_hash=_token_hash(token),
        target_email=user.recovery_email,
        target_email_fingerprint=user.recovery_email_fingerprint,
        auth_version_snapshot=user.auth_version,
        expires_at=now + timedelta(seconds=settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS),
    )
    db.add(token_row)
    enqueue_recovery_email(
        db,
        kind=PASSWORD_RESET_EMAIL,
        recipient=stored_email,
        token=token,
        token_row=token_row,
        expires_at=token_row.expires_at,
    )
    return token


def request_password_reset_for_user(db: Session, user: User) -> tuple[str, str]:
    """Queue recovery mail for an administrator-selected account.

    The administrator never receives the opaque reset token or the complete
    address.  This helper merely avoids asking support staff to know or enter a
    user's private recovery address.
    """

    require_email_delivery()
    expected_auth_version = int(user.auth_version or 0)
    lock_active_user(db, user.id)
    db.refresh(user)
    ensure_active_user(user)
    stored_email = reveal(user.recovery_email)
    if (
        not stored_email
        or user.recovery_email_verified_at is None
        or not user.recovery_email_fingerprint
        or fingerprint(stored_email) != user.recovery_email_fingerprint
        or int(user.auth_version or 0) != expected_auth_version
    ):
        db.rollback()
        raise BizError(
            "该账号未绑定已验证的找回邮箱；请让用户使用已绑定的 KAI 身份登录，或先完成身份核验后绑定邮箱",
            status_code=409,
        )
    token = _queue_password_reset_for_user(db, user, stored_email)
    # Deliberately leave commit ownership to the privileged account-action
    # service so the mail outbox and immutable admin audit row commit together.
    return token, stored_email


def issue_kai_recovery_token(db: Session, user: User) -> str:
    """Issue reset proof after the caller has completed a fresh KAI OIDC flow."""

    ensure_active_user(user)
    _refresh_locked_user(db, user)
    now = utcnow()
    _expire_open_tokens(db, user.id, (PASSWORD_RESET_KAI,), now)
    token = _new_token()
    db.add(AccountRecoveryToken(
        user_id=user.id,
        purpose=PASSWORD_RESET_KAI,
        token_hash=_token_hash(token),
        auth_version_snapshot=user.auth_version,
        expires_at=now + timedelta(seconds=settings.ACCOUNT_RECOVERY_KAI_TTL_SECONDS),
    ))
    db.commit()
    return token


def _set_password_and_revoke(db: Session, user: User, password: str, now=None) -> None:
    changed_at = now or utcnow()
    user.password = hash_password(password)
    user.password_set = True
    user.auth_version = int(user.auth_version or 0) + 1
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    ).update({AuthSession.revoked_at: changed_at}, synchronize_session=False)
    _expire_open_tokens(db, user.id, (VERIFY_EMAIL, *RESET_PURPOSES), changed_at)


def reset_password(db: Session, token: str, password: str) -> str | None:
    now = utcnow()
    row = db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.token_hash == _token_hash(token),
        AccountRecoveryToken.purpose.in_(RESET_PURPOSES),
        AccountRecoveryToken.consumed_at.is_(None),
        AccountRecoveryToken.expires_at >= now,
    ).first()
    if not row:
        raise BizError(INVALID_TOKEN_MESSAGE)
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise BizError(INVALID_TOKEN_MESSAGE)
    lock_active_user(db, user.id)
    db.refresh(user)
    db.refresh(row)
    ensure_active_user(user)
    now = utcnow()
    if (
        row.consumed_at is not None
        or row.expires_at < now
        or row.auth_version_snapshot != int(user.auth_version or 0)
    ):
        db.rollback()
        raise BizError(INVALID_TOKEN_MESSAGE)
    consumed = db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.id == row.id,
        AccountRecoveryToken.consumed_at.is_(None),
        AccountRecoveryToken.expires_at >= now,
        AccountRecoveryToken.auth_version_snapshot == int(user.auth_version or 0),
    ).update({AccountRecoveryToken.consumed_at: now}, synchronize_session=False)
    if consumed != 1:
        db.rollback()
        raise BizError(INVALID_TOKEN_MESSAGE)
    notification_email = reveal(user.recovery_email)
    if (
        not user.recovery_email_verified_at
        or not notification_email
        or fingerprint(notification_email) != user.recovery_email_fingerprint
    ):
        notification_email = ""
    _set_password_and_revoke(db, user, password, now)
    if notification_email:
        enqueue_password_changed_notice(
            db,
            user_id=user.id,
            recipient=notification_email,
            expires_at=now + timedelta(
                seconds=settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS
            ),
        )
    db.commit()
    return notification_email or None


def change_password_and_revoke_other_sessions(
    db: Session,
    user: User,
    current_password: str,
    password: str,
    current_session_id: str | None,
) -> int:
    """Change an authenticated user's password without ejecting this device."""

    ensure_active_user(user)
    expected_auth_version = int(user.auth_version or 0)
    _refresh_locked_user(
        db,
        user,
        expected_auth_version=expected_auth_version,
        current_session_id=current_session_id,
    )
    if not verify_password(current_password, user.password):
        db.rollback()
        raise BizError("原密码错误")
    changed_at = utcnow()
    user.password = hash_password(password)
    user.password_set = True
    sessions = db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    )
    if current_session_id:
        sessions = sessions.filter(AuthSession.id != current_session_id)
    revoked = sessions.update(
        {AuthSession.revoked_at: changed_at},
        synchronize_session=False,
    )
    # Proofs issued before the authenticated password change must not remain
    # usable, even though the current device's JWT remains valid.
    _expire_open_tokens(db, user.id, (VERIFY_EMAIL, *RESET_PURPOSES), changed_at)
    db.commit()
    return revoked
