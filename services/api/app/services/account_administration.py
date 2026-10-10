"""Privileged account lifecycle operations with durable audit and revocation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.account_admin_action import AccountAdminAction
from app.models.account_deletion import AccountDeletionRequest
from app.models.account_recovery import AccountRecoveryToken
from app.models.auth_session import AuthSession
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.admin_account import AdminUserActionIn
from app.services import account_recovery
from app.services.account_deletion_data import get_deletion_blockers
from app.services.auth_session import utcnow
from app.utils.response import BizError


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def action_out(row: AccountAdminAction) -> dict:
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "target_user_id": row.target_user_id,
        "action": row.action,
        "reason": row.reason,
        "previous_status": row.previous_status,
        "new_status": row.new_status,
        "result_code": row.result_code,
        "created_at": row.created_at,
    }


def _matching_retry(
    row: AccountAdminAction | None,
    *,
    actor_user_id: int,
    target_user_id: int,
    data: AdminUserActionIn,
) -> dict | None:
    if row is None:
        return None
    if (
        row.actor_user_id != actor_user_id
        or row.target_user_id != target_user_id
        or row.action != data.action
        or row.reason != data.reason
    ):
        raise BizError("该幂等编号已用于另一项账号操作", status_code=409)
    return action_out(row)


def _revoke_all_credentials(db: Session, user: User) -> None:
    now = utcnow()
    user.auth_version = int(user.auth_version or 0) + 1
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    ).update({AuthSession.revoked_at: now}, synchronize_session=False)
    db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.user_id == user.id,
        AccountRecoveryToken.consumed_at.is_(None),
    ).update({AccountRecoveryToken.consumed_at: now}, synchronize_session=False)


def _target(db: Session, actor: User, target_user_id: int) -> User:
    target = db.get(User, target_user_id)
    if target is None:
        raise BizError("用户不存在", status_code=404)
    if target.id == actor.id:
        raise BizError("管理员不能在账号管理页操作自己的账号", status_code=403)
    if target.role == "admin":
        raise BizError("管理员账号必须通过受控权限交接流程处理", status_code=403)
    return target


def _lock_target(db: Session, target: User, allowed_statuses: tuple[str, ...]) -> None:
    changed = db.connection().execute(
        update(User.__table__).where(
            User.id == target.id,
            User.account_status.in_(allowed_statuses),
        ).values(account_status=User.account_status)
    )
    if changed.rowcount != 1:
        db.rollback()
        db.refresh(target)
        raise BizError("账号状态已变化，请刷新后重试", status_code=409)
    db.refresh(target)


def _record(
    db: Session,
    *,
    actor: User,
    target: User,
    data: AdminUserActionIn,
    previous_status: str,
    result_code: str,
) -> AccountAdminAction:
    row = AccountAdminAction(
        actor_user_id=actor.id,
        target_user_id=target.id,
        action=data.action,
        client_request_id=data.client_request_id,
        reason=data.reason,
        previous_status=previous_status,
        new_status=target.account_status,
        result_code=result_code,
    )
    db.add(row)
    return row


def perform_user_action(
    db: Session,
    *,
    actor: User,
    target_user_id: int,
    data: AdminUserActionIn,
) -> dict:
    existing = db.query(AccountAdminAction).filter(
        AccountAdminAction.client_request_id == data.client_request_id
    ).first()
    retried = _matching_retry(
        existing,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        data=data,
    )
    if retried:
        return retried

    target = _target(db, actor, target_user_id)
    allowed = {
        "send_password_reset": ("active",),
        "issue_password_reset_code": ("active",),
        "freeze": ("active",),
        "unfreeze": ("suspended",),
        "delete": ("active", "suspended"),
    }[data.action]
    _lock_target(db, target, allowed)

    # Recheck after the target row fence so concurrent retries cannot create
    # duplicate mail, revocations, or deletion jobs.
    existing = db.query(AccountAdminAction).filter(
        AccountAdminAction.client_request_id == data.client_request_id
    ).first()
    retried = _matching_retry(
        existing,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        data=data,
    )
    if retried:
        db.rollback()
        return retried

    previous_status = target.account_status
    result_code = "completed"

    if data.action == "send_password_reset":
        row = _record(
            db,
            actor=actor,
            target=target,
            data=data,
            previous_status=previous_status,
            result_code="reset_email_queued",
        )
        account_recovery.request_password_reset_for_user(db, target)
    elif data.action == "issue_password_reset_code":
        if (data.confirm_username or "").strip() != target.username:
            raise BizError("请输入完整用户名以确认生成重置码", status_code=400)
        reset_token, reset_expires_at = account_recovery.issue_admin_password_reset_token(
            db,
            target,
        )
        row = _record(
            db,
            actor=actor,
            target=target,
            data=data,
            previous_status=previous_status,
            result_code="reset_code_issued",
        )
    elif data.action == "freeze":
        target.account_status = "suspended"
        _revoke_all_credentials(db, target)
        supplier = db.query(Supplier).filter(Supplier.user_id == target.id).first()
        if supplier and supplier.status == "approved":
            supplier.status = "suspended"
            target.supplier_status = "suspended"
            db.query(Product).filter(
                Product.supplier_id == supplier.id,
                Product.status == "on",
            ).update({
                Product.status: "off",
                Product.version: Product.version + 1,
            }, synchronize_session=False)
        row = _record(
            db,
            actor=actor,
            target=target,
            data=data,
            previous_status=previous_status,
            result_code=result_code,
        )
    elif data.action == "unfreeze":
        target.account_status = "active"
        _revoke_all_credentials(db, target)
        row = _record(
            db,
            actor=actor,
            target=target,
            data=data,
            previous_status=previous_status,
            result_code=result_code,
        )
    else:
        if (data.confirm_username or "").strip() != target.username:
            raise BizError("请输入完整用户名以确认注销账号", status_code=400)
        blockers = get_deletion_blockers(db, target)
        if blockers:
            summary = "；".join(item["message"] for item in blockers[:3])
            raise BizError(f"账号存在未结事项，暂不能注销：{summary}", status_code=409)
        now = utcnow()
        target.account_status = "deleting"
        _revoke_all_credentials(db, target)
        db.query(AccountDeletionRequest).filter(
            AccountDeletionRequest.user_id == target.id,
            AccountDeletionRequest.status.in_(("verified", "blocked")),
        ).update(
            {AccountDeletionRequest.receipt_expires_at: now},
            synchronize_session=False,
        )
        seed = secrets.token_urlsafe(32)
        deletion = AccountDeletionRequest(
            user_id=target.id,
            ticket_hash=_digest(f"admin-ticket:{seed}"),
            credential_digest=_digest(f"admin-action:{data.client_request_id}"),
            status="processing",
            expires_at=now + timedelta(minutes=10),
            receipt_expires_at=now + timedelta(days=7),
            requested_at=now,
            cleanup_paths=[],
            retry_at=now,
        )
        db.add(deletion)
        row = _record(
            db,
            actor=actor,
            target=target,
            data=data,
            previous_status=previous_status,
            result_code="deletion_queued",
        )

    db.commit()
    db.refresh(row)
    result = action_out(row)
    if data.action == "issue_password_reset_code":
        # Never persist or expose this value through history/idempotent replay.
        # It is deliberately present only in the first successful response.
        result["reset_token"] = reset_token
        result["reset_expires_at"] = reset_expires_at
    return result


def list_user_actions(
    db: Session,
    *,
    target_user_id: int,
    page: int,
    page_size: int,
) -> dict:
    if db.get(User, target_user_id) is None:
        raise BizError("用户不存在", status_code=404)
    query = db.query(AccountAdminAction).filter(
        AccountAdminAction.target_user_id == target_user_id
    )
    total = query.count()
    rows = query.order_by(
        AccountAdminAction.created_at.desc(), AccountAdminAction.id.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [action_out(row) for row in rows],
    }
