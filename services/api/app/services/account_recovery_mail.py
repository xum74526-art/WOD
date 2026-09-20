"""Transactional account-recovery mail outbox and bounded SMTP worker."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sensitive import protect, reveal
from app.db.session import SessionLocal
from app.integrations import account_email
from app.models.account_recovery import AccountRecoveryToken
from app.models.account_recovery_mail import AccountRecoveryMailOutbox
from app.models.user import User
from app.services.auth_session import utcnow
from app.utils.email_address import normalize_email


logger = logging.getLogger(__name__)

VERIFY_EMAIL = "verify_email"
PASSWORD_RESET_EMAIL = "password_reset_email"
PASSWORD_CHANGED_NOTICE = "password_changed_notice"
DELIVERABLE_KINDS = (VERIFY_EMAIL, PASSWORD_RESET_EMAIL, PASSWORD_CHANGED_NOTICE)
CLAIMABLE_STATUSES = ("pending", "retry")
TERMINAL_STATUSES = ("delivered", "suppressed", "failed", "expired", "canceled")


@dataclass(frozen=True)
class ClaimedMail:
    job_id: int
    attempt: int
    kind: str
    recipient: str
    token: str | None
    expires_at: datetime


def enqueue_recovery_email(
    db: Session,
    *,
    kind: str,
    recipient: str,
    token: str,
    token_row: AccountRecoveryToken,
    expires_at: datetime,
) -> AccountRecoveryMailOutbox:
    """Stage a deliverable message in the caller's current transaction."""

    if kind not in (VERIFY_EMAIL, PASSWORD_RESET_EMAIL):
        raise ValueError("unsupported_recovery_mail_kind")
    if token_row.id is None:
        db.flush()
    normalized = normalize_email(recipient)
    row = AccountRecoveryMailOutbox(
        user_id=token_row.user_id,
        recovery_token_id=token_row.id,
        kind=kind,
        recipient_payload=protect(normalized),
        token_payload=protect(token),
        status="pending",
        available_at=utcnow(),
        expires_at=expires_at,
    )
    db.add(row)
    return row


def enqueue_suppressed_password_reset(
    db: Session,
    *,
    recipient: str,
    expires_at: datetime,
) -> AccountRecoveryMailOutbox:
    """Stage a non-deliverable row for an unrecognised public address.

    Dummy encryption makes the expensive local work and database write much
    closer to a real request, but the resulting ciphertext is discarded before
    commit. No usable proof is created and SMTP is never asked to deliver to an
    unverified address.
    """

    now = utcnow()
    # Perform the same normalization, random-token generation and field-level
    # encryption work as a deliverable request, then discard it.  A terminal
    # anti-enumeration row must never retain an address that ZTW has not
    # established belongs to one of its accounts.
    protected_recipient = protect(normalize_email(recipient))
    protected_token = protect(secrets.token_urlsafe(32))
    if not protected_recipient or not protected_token:
        raise RuntimeError("suppressed_recovery_payload_protection_failed")
    row = AccountRecoveryMailOutbox(
        user_id=None,
        recovery_token_id=None,
        kind=PASSWORD_RESET_EMAIL,
        recipient_payload=None,
        token_payload=None,
        status="suppressed",
        attempts=0,
        available_at=now,
        expires_at=expires_at,
        finished_at=now,
    )
    db.add(row)
    return row


def enqueue_password_changed_notice(
    db: Session,
    *,
    user_id: int,
    recipient: str,
    expires_at: datetime,
) -> AccountRecoveryMailOutbox:
    """Stage a security notice in the password-change transaction."""

    row = AccountRecoveryMailOutbox(
        user_id=user_id,
        recovery_token_id=None,
        kind=PASSWORD_CHANGED_NOTICE,
        recipient_payload=protect(normalize_email(recipient)),
        token_payload=None,
        status="pending",
        available_at=utcnow(),
        expires_at=expires_at,
    )
    db.add(row)
    return row


def _terminal_values(status: str, now: datetime, error_code: str | None = None) -> dict:
    return {
        AccountRecoveryMailOutbox.status: status,
        AccountRecoveryMailOutbox.recipient_payload: None,
        AccountRecoveryMailOutbox.token_payload: None,
        AccountRecoveryMailOutbox.locked_at: None,
        AccountRecoveryMailOutbox.last_error_code: error_code,
        AccountRecoveryMailOutbox.finished_at: now,
        AccountRecoveryMailOutbox.updated_at: now,
    }


def _perform_maintenance(db: Session, now: datetime) -> None:
    """Recover abandoned leases, expire secrets and purge old terminal rows."""

    # One SMTP operation can perform several socket-bound steps.  Keep the
    # lease well above the configured per-operation timeout so another API
    # worker does not normally reclaim a message while the first still owns a
    # live provider connection.
    lease_seconds = max(
        30,
        int(settings.ACCOUNT_RECOVERY_MAIL_LEASE_SECONDS),
        int(max(1.0, settings.ACCOUNT_RECOVERY_SMTP_TIMEOUT_SECONDS) * 6),
    )
    stale_before = now - timedelta(seconds=lease_seconds)
    db.query(AccountRecoveryMailOutbox).filter(
        AccountRecoveryMailOutbox.status == "sending",
        AccountRecoveryMailOutbox.locked_at.is_not(None),
        AccountRecoveryMailOutbox.locked_at <= stale_before,
        AccountRecoveryMailOutbox.expires_at > now,
    ).update(
        {
            AccountRecoveryMailOutbox.status: "retry",
            AccountRecoveryMailOutbox.available_at: now,
            AccountRecoveryMailOutbox.locked_at: None,
            AccountRecoveryMailOutbox.last_error_code: "delivery_lease_expired",
            AccountRecoveryMailOutbox.updated_at: now,
        },
        synchronize_session=False,
    )
    db.query(AccountRecoveryMailOutbox).filter(
        AccountRecoveryMailOutbox.status.in_((*CLAIMABLE_STATUSES, "sending")),
        AccountRecoveryMailOutbox.expires_at <= now,
    ).update(_terminal_values("expired", now), synchronize_session=False)

    retention_seconds = max(
        60, int(settings.ACCOUNT_RECOVERY_MAIL_RETENTION_SECONDS)
    )
    purge_before = now - timedelta(seconds=retention_seconds)
    # Once a proof is consumed or expires, its delivery-only copy of the
    # address has no further business purpose. Clear it even while the minimal
    # token audit row remains inside the short retention window.
    db.query(AccountRecoveryToken).filter(
        or_(
            AccountRecoveryToken.consumed_at.is_not(None),
            AccountRecoveryToken.expires_at <= now,
        ),
        or_(
            AccountRecoveryToken.target_email.is_not(None),
            AccountRecoveryToken.target_email_fingerprint.is_not(None),
        ),
    ).update(
        {
            AccountRecoveryToken.target_email: None,
            AccountRecoveryToken.target_email_fingerprint: None,
        },
        synchronize_session=False,
    )
    db.query(AccountRecoveryMailOutbox).filter(
        AccountRecoveryMailOutbox.status.in_(TERMINAL_STATUSES),
        AccountRecoveryMailOutbox.finished_at.is_not(None),
        AccountRecoveryMailOutbox.finished_at <= purge_before,
    ).delete(synchronize_session=False)
    outbox_reference = db.query(AccountRecoveryMailOutbox.id).filter(
        AccountRecoveryMailOutbox.recovery_token_id == AccountRecoveryToken.id
    ).exists()
    db.query(AccountRecoveryToken).filter(
        or_(
            AccountRecoveryToken.consumed_at <= purge_before,
            AccountRecoveryToken.expires_at <= purge_before,
        ),
        ~outbox_reference,
    ).delete(synchronize_session=False)


def _claim_one(
    session_factory: Callable[[], Session],
    now: datetime,
) -> ClaimedMail | None:
    """Claim one row with a compare-and-swap that works across API workers."""

    db = session_factory()
    try:
        _perform_maintenance(db, now)
        db.commit()
        candidates = db.query(
            AccountRecoveryMailOutbox.id,
            AccountRecoveryMailOutbox.status,
            AccountRecoveryMailOutbox.attempts,
        ).filter(
            AccountRecoveryMailOutbox.status.in_(CLAIMABLE_STATUSES),
            AccountRecoveryMailOutbox.available_at <= now,
            AccountRecoveryMailOutbox.expires_at > now,
        ).order_by(
            AccountRecoveryMailOutbox.available_at.asc(),
            AccountRecoveryMailOutbox.id.asc(),
        ).limit(8).all()
        for candidate_id, prior_status, prior_attempts_value in candidates:
            prior_attempts = int(prior_attempts_value or 0)
            attempt = prior_attempts + 1
            claimed = _try_claim_snapshot(
                db,
                job_id=candidate_id,
                prior_status=prior_status,
                prior_attempts=prior_attempts,
                now=now,
            )
            if not claimed:
                db.rollback()
                continue
            db.commit()
            row = db.get(AccountRecoveryMailOutbox, candidate_id)
            if row is None:
                return None
            recipient = reveal(row.recipient_payload)
            token = reveal(row.token_payload) if row.token_payload else None
            payload_valid = bool(recipient and row.kind in DELIVERABLE_KINDS)
            token_row = None
            if row.kind in (VERIFY_EMAIL, PASSWORD_RESET_EMAIL):
                token_row = (
                    db.get(AccountRecoveryToken, row.recovery_token_id)
                    if row.recovery_token_id is not None
                    else None
                )
                user = (
                    db.get(User, token_row.user_id)
                    if token_row is not None
                    else None
                )
                payload_valid = bool(
                    payload_valid
                    and token
                    and token_row
                    and user
                    and row.user_id == user.id
                    and user.account_status == "active"
                    and token_row.auth_version_snapshot
                    == int(user.auth_version or 0)
                    and token_row.consumed_at is None
                    and token_row.expires_at >= now
                    and token_row.token_hash
                    == hashlib.sha256(token.encode("utf-8")).hexdigest()
                )
            if payload_valid:
                try:
                    recipient = normalize_email(recipient)
                except ValueError:
                    payload_valid = False
            if not payload_valid:
                db.query(AccountRecoveryMailOutbox).filter(
                    AccountRecoveryMailOutbox.id == row.id,
                    AccountRecoveryMailOutbox.status == "sending",
                    AccountRecoveryMailOutbox.attempts == attempt,
                ).update(
                    _terminal_values("canceled", now, "invalid_or_stale_payload"),
                    synchronize_session=False,
                )
                db.commit()
                continue
            return ClaimedMail(
                job_id=row.id,
                attempt=attempt,
                kind=row.kind,
                recipient=recipient,
                token=token,
                expires_at=row.expires_at,
            )
        return None
    finally:
        db.close()


def _try_claim_snapshot(
    db: Session,
    *,
    job_id: int,
    prior_status: str,
    prior_attempts: int,
    now: datetime,
) -> bool:
    """CAS a primitive candidate snapshot; never refresh stale ORM state."""

    if prior_status not in CLAIMABLE_STATUSES:
        return False
    claimed = db.query(AccountRecoveryMailOutbox).filter(
        AccountRecoveryMailOutbox.id == job_id,
        AccountRecoveryMailOutbox.status.in_(CLAIMABLE_STATUSES),
        AccountRecoveryMailOutbox.status == prior_status,
        AccountRecoveryMailOutbox.attempts == prior_attempts,
        AccountRecoveryMailOutbox.available_at <= now,
        AccountRecoveryMailOutbox.expires_at > now,
    ).update(
        {
            AccountRecoveryMailOutbox.status: "sending",
            AccountRecoveryMailOutbox.attempts: prior_attempts + 1,
            AccountRecoveryMailOutbox.locked_at: now,
            AccountRecoveryMailOutbox.updated_at: now,
        },
        synchronize_session=False,
    )
    return claimed == 1


def _mark_delivered(
    session_factory: Callable[[], Session],
    claim: ClaimedMail,
    now: datetime,
) -> bool:
    db = session_factory()
    try:
        values = _terminal_values("delivered", now)
        values[AccountRecoveryMailOutbox.delivered_at] = now
        updated = db.query(AccountRecoveryMailOutbox).filter(
            AccountRecoveryMailOutbox.id == claim.job_id,
            AccountRecoveryMailOutbox.status == "sending",
            AccountRecoveryMailOutbox.attempts == claim.attempt,
        ).update(values, synchronize_session=False)
        db.commit()
        return updated == 1
    finally:
        db.close()


def _mark_failed_attempt(
    session_factory: Callable[[], Session],
    claim: ClaimedMail,
    now: datetime,
    error_code: str,
) -> str:
    db = session_factory()
    try:
        maximum = max(1, int(settings.ACCOUNT_RECOVERY_MAIL_MAX_ATTEMPTS))
        base = max(1, int(settings.ACCOUNT_RECOVERY_MAIL_RETRY_BASE_SECONDS))
        ceiling = max(base, int(settings.ACCOUNT_RECOVERY_MAIL_RETRY_MAX_SECONDS))
        exponent = min(20, max(0, claim.attempt - 1))
        delay = min(ceiling, base * (2 ** exponent))
        retry_at = now + timedelta(seconds=delay)
        if claim.attempt >= maximum or retry_at >= claim.expires_at:
            status = "failed"
            values = _terminal_values(status, now, error_code)
        else:
            status = "retry"
            values = {
                AccountRecoveryMailOutbox.status: status,
                AccountRecoveryMailOutbox.available_at: retry_at,
                AccountRecoveryMailOutbox.locked_at: None,
                AccountRecoveryMailOutbox.last_error_code: error_code,
                AccountRecoveryMailOutbox.updated_at: now,
            }
        updated = db.query(AccountRecoveryMailOutbox).filter(
            AccountRecoveryMailOutbox.id == claim.job_id,
            AccountRecoveryMailOutbox.status == "sending",
            AccountRecoveryMailOutbox.attempts == claim.attempt,
        ).update(values, synchronize_session=False)
        db.commit()
        return status if updated == 1 else "claim_lost"
    finally:
        db.close()


def process_account_recovery_mail_outbox(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    batch_size: int | None = None,
) -> dict[str, int]:
    """Deliver a bounded batch; every diagnostic is free of payload values."""

    result = {"claimed": 0, "delivered": 0, "retried": 0, "failed": 0}
    if not account_email.email_delivery_configured():
        # Maintenance still removes expired encrypted payloads while delivery
        # is deliberately paused by configuration.
        db = session_factory()
        try:
            _perform_maintenance(db, utcnow())
            db.commit()
        finally:
            db.close()
        return result

    limit = batch_size
    if limit is None:
        limit = settings.ACCOUNT_RECOVERY_MAIL_BATCH_SIZE
    limit = max(1, min(100, int(limit)))
    for _ in range(limit):
        claim = _claim_one(session_factory, utcnow())
        if claim is None:
            break
        result["claimed"] += 1
        try:
            if claim.kind == PASSWORD_CHANGED_NOTICE:
                account_email.send_password_changed_notice(claim.recipient)
            else:
                account_email.send_account_recovery_email(
                    claim.kind, claim.recipient, claim.token or ""
                )
        except Exception as error:  # Provider details and payloads never enter logs.
            error_code = type(error).__name__[:64]
            status = _mark_failed_attempt(
                session_factory, claim, utcnow(), error_code
            )
            if status == "retry":
                result["retried"] += 1
            elif status == "failed":
                result["failed"] += 1
            logger.warning(
                "account_recovery_mail_attempt_failed job_id=%s kind=%s "
                "attempt=%s status=%s error_type=%s",
                claim.job_id,
                claim.kind,
                claim.attempt,
                status,
                error_code,
            )
            continue
        if _mark_delivered(session_factory, claim, utcnow()):
            result["delivered"] += 1
    return result


def dispatch_account_recovery_mail() -> dict[str, int]:
    """Scheduler boundary that never lets database/provider details escape."""

    try:
        return process_account_recovery_mail_outbox()
    except Exception as error:
        logger.error(
            "account_recovery_mail_worker_failed error_type=%s",
            type(error).__name__,
        )
        return {"claimed": 0, "delivered": 0, "retried": 0, "failed": 0}
