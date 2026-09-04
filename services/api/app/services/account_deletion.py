"""Account deletion state machine and retryable, narrowly scoped file cleanup.

Only a freshly password-verified, deletion-scoped capability may submit. The
capability is carried in a POST body, hashed at rest and never logged. Money,
order and reward rules remain owned by their existing services.
"""
from datetime import timedelta, timezone
import hashlib
from pathlib import Path
import re
import secrets

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.db.session import SessionLocal
from app.models.account_deletion import AccountDeletionRequest
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.account_lifecycle import lock_active_user
from app.services.auth_session import utcnow
from app.utils.response import BizError


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def eligibility(db: Session, user: User) -> dict:
    from app.services.account_deletion_data import get_deletion_blockers, get_automatic_actions
    blockers = get_deletion_blockers(db, user)
    if user.role not in ("personal", "supplier"):
        blockers.append({"code": "privileged_account", "message": "平台管理账号须先完成管理权限交接，不能通过普通账号入口注销。", "count": 1})
    return {"eligible": not blockers, "blockers": blockers, "automatic_actions": get_automatic_actions(db, user)}


def verify_deletion_password(db: Session, user: User, password: str) -> dict:
    if not verify_password(password, user.password):
        raise BizError("原密码不正确，请使用 WOD 账号密码验证")
    lock_active_user(db, user.id)
    # Re-read after the lock: a password change may have won the race.
    db.refresh(user)
    if not verify_password(password, user.password):
        raise BizError("密码已变更，请重新验证")
    ticket = secrets.token_urlsafe(32)
    now = utcnow()
    row = AccountDeletionRequest(
        user_id=user.id, ticket_hash=_digest(ticket),
        credential_digest=_digest(user.password), status="verified",
        expires_at=now + timedelta(minutes=10),
        receipt_expires_at=now + timedelta(days=7), cleanup_paths=[],
    )
    db.add(row)
    db.commit()
    return {"ticket": ticket, "expires_at": row.expires_at.replace(tzinfo=timezone.utc)}


def _request(db: Session, ticket: str) -> AccountDeletionRequest:
    row = db.query(AccountDeletionRequest).filter(
        AccountDeletionRequest.ticket_hash == _digest(ticket),
    ).first()
    if row is None or row.receipt_expires_at < utcnow():
        raise BizError("注销验证凭据无效或已过期", status_code=401)
    return row


def deletion_status(db: Session, ticket: str) -> dict:
    row = _request(db, ticket)
    blockers = []
    if row.status == "blocked" or (row.status == "processing" and row.data_scrubbed_at is None):
        user = db.get(User, row.user_id)
        blockers = eligibility(db, user)["blockers"] if user else []
    if row.status == "processing" and row.last_error_code == "cleanup_retry_required":
        blockers.append({"code": "cleanup_retry_required", "message": "部分资料清理暂未完成，系统会自动重试；如持续未完成，请联系平台核查。", "count": 1})
    return {"status": row.status, "blockers": blockers,
            "completed_at": row.completed_at.replace(tzinfo=timezone.utc) if row.completed_at else None}


def submit_deletion(db: Session, ticket: str, confirm: bool) -> dict:
    if confirm is not True:
        raise BizError("请明确确认注销账号及相关数据处理")
    row = _request(db, ticket)
    if row.status in ("processing", "completed"):
        return deletion_status(db, ticket)
    if row.expires_at < utcnow():
        raise BizError("注销身份验证已过期，请重新验证", status_code=400)
    # Lock the row even when a concurrent retry has already marked it deleting.
    # Rechecking the request after this fence makes duplicate submits idempotent.
    db.connection().execute(update(User.__table__).where(
        User.id == row.user_id,
    ).values(account_status=User.account_status))
    # Expire stale ORM state after the transaction fence.
    db.refresh(row)
    if row.status in ("processing", "completed"):
        return deletion_status(db, ticket)
    if row.expires_at < utcnow() or row.receipt_expires_at < utcnow():
        raise BizError("注销身份验证已过期，请重新验证")
    lock_active_user(db, row.user_id)
    user = db.get(User, row.user_id, populate_existing=True)
    if not secrets.compare_digest(row.credential_digest, _digest(user.password)):
        raise BizError("账号密码已变更，请重新验证")
    result = eligibility(db, user)
    if not result["eligible"]:
        row.status = "blocked"
        db.commit()
        return {"status": "blocked", "blockers": result["blockers"], "completed_at": None}
    db.info["account_deletion_worker"] = True
    try:
        user.account_status = "deleting"
        row.status = "processing"
        row.requested_at = utcnow()
        row.credential_digest = ""
        db.query(AuthSession).filter(AuthSession.user_id == user.id).update(
            {AuthSession.revoked_at: utcnow()}, synchronize_session=False,
        )
        # A second pre-issued capability must not start a second cleanup job.
        db.query(AccountDeletionRequest).filter(
            AccountDeletionRequest.user_id == user.id,
            AccountDeletionRequest.id != row.id,
        ).update({AccountDeletionRequest.receipt_expires_at: utcnow()}, synchronize_session=False)
        db.commit()
    finally:
        db.info.pop("account_deletion_worker", None)
    return {"status": "processing", "blockers": [], "completed_at": None}


def upload_root() -> Path:
    return (Path(settings.UPLOAD_ROOT).expanduser().resolve() if settings.UPLOAD_ROOT
            else Path(__file__).resolve().parents[2] / "uploads")


def _owned_path(root: Path, relative: str, user_id: int) -> Path:
    # Never accept URLs, arbitrary absolute paths, traversal or other users'
    # filenames, even when a historical database row contains one.
    patterns = (
        rf"avatars/avatar_{user_id}\.(jpg|png|webp)",
        rf"id_cards/id_(front|back)_{user_id}\.(jpg|png|webp)",
        rf"community/{user_id}/[0-9a-f]{{32}}\.(jpg|png|webp|mp4|webm)",
    )
    if not any(re.fullmatch(pattern, relative) for pattern in patterns):
        raise ValueError("unowned_cleanup_path")
    path = root / relative
    if _is_link(path) or any(_is_link(parent) for parent in path.parents if parent != root):
        raise ValueError("symlink_cleanup_path")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe_cleanup_path")
    return path


def _is_link(path: Path) -> bool:
    # Windows junctions can point at another account inside the upload root,
    # so containment alone is insufficient even when the target stays inside.
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _orphan_media(root: Path, user_id: int) -> list[str]:
    directory = root / "community" / str(user_id)
    if not directory.exists():
        return []
    if _is_link(directory) or _is_link(root / "community"):
        raise ValueError("symlink_cleanup_directory")
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe_cleanup_directory")
    result = []
    for path in directory.iterdir():
        relative = f"community/{user_id}/{path.name}"
        _owned_path(root, relative, user_id)
        result.append(relative)
    return result


def process_deletion(db: Session, request_id: int, *, root: Path | None = None) -> bool:
    """Resume a durable job. False means retry pending, never false completion."""
    from app.services.account_deletion_data import scrub_account_data
    root = (root or upload_root()).resolve()
    db.info["account_deletion_worker"] = True
    try:
        row = db.get(AccountDeletionRequest, request_id, populate_existing=True)
        if row is None or row.status != "processing":
            return bool(row and row.status == "completed")
        changed = db.connection().execute(update(User.__table__).where(
            User.id == row.user_id, User.account_status == "deleting",
        ).values(account_status="deleting"))
        if changed.rowcount != 1:
            raise ValueError("invalid_deletion_state")
        db.refresh(row)
        user = db.get(User, row.user_id, populate_existing=True)
        if row.data_scrubbed_at is None:
            # Recheck after the asynchronous gap (e.g. a delayed payment
            # callback). Never remove identity while a newly found right is open.
            if eligibility(db, user)["blockers"]:
                row.last_error_code = "obligations_require_review"
                row.retry_at = utcnow() + timedelta(minutes=5)
                db.commit()
                return False
            paths = scrub_account_data(db, user)
            paths += _orphan_media(root, user.id)
            # Validate before committing personal data cleanup, and persist
            # the outbox so a crash between DB commit and unlink is recoverable.
            for path in paths:
                _owned_path(root, path, user.id)
            row.cleanup_paths = sorted(set(paths))
            row.data_scrubbed_at = utcnow()
            db.commit()
        for relative in row.cleanup_paths:
            path = _owned_path(root, relative, row.user_id)
            path.unlink(missing_ok=True)
        row.cleanup_paths = []
        row.last_error_code = None
        row.completed_at = utcnow()
        row.status = "completed"
        user.account_status = "deleted"
        user.deleted_at = row.completed_at
        db.commit()
        return True
    except Exception:
        db.rollback()
        # Do not persist/log exception messages: paths and SQL parameters may
        # include private data. Keep a non-sensitive operational failure code.
        row = db.get(AccountDeletionRequest, request_id, populate_existing=True)
        if row and row.status == "processing":
            row.last_error_code = "cleanup_retry_required"
            row.retry_at = utcnow() + timedelta(minutes=5)
            db.commit()
        return False
    finally:
        db.info.pop("account_deletion_worker", None)


def resume_deletions() -> None:
    """Only existing, explicitly confirmed requests are processed by this job."""
    with SessionLocal() as db:
        ids = [item[0] for item in db.query(AccountDeletionRequest.id).filter(
            AccountDeletionRequest.status == "processing",
            AccountDeletionRequest.retry_at <= utcnow(),
        ).order_by(AccountDeletionRequest.id).limit(25).all()]
    for request_id in ids:
        with SessionLocal() as db:
            process_deletion(db, request_id)


def process_ticket(ticket: str) -> None:
    with SessionLocal() as db:
        try:
            row = _request(db, ticket)
            process_deletion(db, row.id)
        except BizError:
            return
