"""Administrator announcements delivered to every active account.

The broadcast record is the durable audit and idempotency boundary.  Recipient
rows are inserted in one database statement so a large active-user set does
not require one ORM round trip per account, while the per-user dedupe key keeps
retries safe.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import exists, insert, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationBroadcast
from app.models.user import User
from app.schemas.notification import (
    NotificationBroadcastCreateIn,
    NotificationBroadcastOut,
    NotificationBroadcastRevokeIn,
)
from app.utils.response import BizError


_BROADCAST_LOCK = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _payload_values(data: NotificationBroadcastCreateIn) -> dict:
    values = data.model_dump()
    # The schema strips these fields, but keeping the service boundary
    # defensive also protects direct callers and future background jobs.
    for field in ("client_request_id", "title", "content", "title_en", "content_en", "action_url"):
        value = values.get(field)
        values[field] = value.strip() if isinstance(value, str) else value
    if not values["title"] or not values["content"]:
        raise BizError("消息标题和正文不能为空")
    expires_at = values.get("expires_at")
    if expires_at is not None:
        values["expires_at"] = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    return values


def _same_payload(row: NotificationBroadcast, values: dict) -> bool:
    return all(
        getattr(row, field) == values.get(field)
        for field in (
            "title",
            "content",
            "title_en",
            "content_en",
            "notification_type",
            "action_url",
            "expires_at",
        )
    )


def _out(row: NotificationBroadcast) -> dict:
    data = NotificationBroadcastOut.model_validate(row).model_dump()
    if row.status == "completed" and row.expires_at is not None and row.expires_at <= _utcnow():
        data["status"] = "expired"
    return data


def list_broadcasts(db: Session, *, page: int, page_size: int) -> dict:
    query = db.query(NotificationBroadcast)
    total = query.count()
    rows = query.order_by(
        NotificationBroadcast.created_at.desc(),
        NotificationBroadcast.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_out(row) for row in rows],
    }


def latest_major_announcement(db: Session) -> dict | None:
    """Return only the public fields of the latest completed major notice."""

    row = db.query(NotificationBroadcast).filter(
        NotificationBroadcast.notification_type == "major_announcement",
        NotificationBroadcast.status == "completed",
        or_(
            NotificationBroadcast.expires_at.is_(None),
            NotificationBroadcast.expires_at > _utcnow(),
        ),
    ).order_by(
        NotificationBroadcast.created_at.desc(),
        NotificationBroadcast.id.desc(),
    ).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "title_en": row.title_en,
        "content_en": row.content_en,
        "action_url": row.action_url,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


def _insert_recipients(db: Session, row: NotificationBroadcast) -> int:
    dedupe_key = f"broadcast:{row.id}"
    recipient_select = select(
        User.id,
        literal(row.title),
        literal(row.content),
        literal(row.title_en),
        literal(row.content_en),
        literal(row.notification_type),
        literal(row.action_url),
        literal(dedupe_key),
        literal(False),
        literal(row.expires_at),
    ).where(
        or_(User.account_status.is_(None), User.account_status == "active"),
        ~exists().where(
            Notification.user_id == User.id,
            Notification.dedupe_key == dedupe_key,
        ),
    )
    db.execute(
        insert(Notification).from_select(
            [
                "user_id",
                "title",
                "content",
                "title_en",
                "content_en",
                "type",
                "action_url",
                "dedupe_key",
                "is_read",
                "expires_at",
            ],
            recipient_select,
        )
    )
    return int(
        db.query(Notification.id)
        .filter(Notification.dedupe_key == dedupe_key)
        .count()
    )


def create_broadcast(
    db: Session,
    *,
    actor_user_id: int,
    data: NotificationBroadcastCreateIn,
) -> dict:
    """Create one all-active-users announcement, safely retryable by request id."""

    values = _payload_values(data)

    # The lock closes the common same-worker race.  The unique database
    # constraint below remains the source of truth when multiple workers race.
    with _BROADCAST_LOCK:
        row = db.query(NotificationBroadcast).filter(
            NotificationBroadcast.client_request_id == values["client_request_id"],
        ).first()
        if row is not None:
            if not _same_payload(row, values):
                raise BizError("消息发布幂等键已用于不同内容", status_code=409)
            if row.actor_user_id != actor_user_id:
                raise BizError("消息发布幂等键已被其他管理员使用", status_code=409)
            if row.status == "completed":
                return _out(row)
            raise BizError("消息发布正在处理中，请稍后重试", status_code=409)

        row = NotificationBroadcast(
            client_request_id=values["client_request_id"],
            actor_user_id=actor_user_id,
            title=values["title"],
            content=values["content"],
            title_en=values.get("title_en"),
            content_en=values.get("content_en"),
            notification_type=values["notification_type"],
            action_url=values.get("action_url"),
            expires_at=values.get("expires_at"),
            audience="all_active",
            status="processing",
            recipient_count=0,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            # Another worker won the unique request-id race.  Re-read it and
            # return its durable result rather than duplicating recipients.
            db.rollback()
            existing = db.query(NotificationBroadcast).filter(
                NotificationBroadcast.client_request_id == values["client_request_id"],
            ).first()
            if existing is None:
                raise
            if not _same_payload(existing, values):
                raise BizError("消息发布幂等键已用于不同内容", status_code=409)
            if existing.actor_user_id != actor_user_id:
                raise BizError("消息发布幂等键已被其他管理员使用", status_code=409)
            if existing.status == "completed":
                return _out(existing)
            raise BizError("消息发布正在处理中，请稍后重试", status_code=409)

        row.recipient_count = _insert_recipients(db, row)
        row.status = "completed"
        row.completed_at = _utcnow()
        db.commit()
        db.refresh(row)
        return _out(row)


def revoke_broadcast(
    db: Session,
    *,
    broadcast_id: int,
    actor_user_id: int,
    data: NotificationBroadcastRevokeIn,
) -> dict:
    """Revoke a publication without destroying its delivery audit trail."""

    with _BROADCAST_LOCK:
        row = db.query(NotificationBroadcast).filter(
            NotificationBroadcast.id == broadcast_id,
        ).with_for_update().first()
        if row is None:
            raise BizError("公告不存在", status_code=404)
        if row.status == "revoked":
            return _out(row)
        if row.status != "completed":
            raise BizError("公告尚未发布完成，暂不能撤销", status_code=409)

        revoked_at = _utcnow()
        row.status = "revoked"
        row.revoked_at = revoked_at
        row.revoked_by_user_id = actor_user_id
        row.revoke_reason = data.reason

        # Recipient rows remain in the database for audit/idempotency, but no
        # account can list or reopen a revoked broadcast after this commit.
        db.query(Notification).filter(
            Notification.dedupe_key == f"broadcast:{row.id}",
            Notification.deleted_at.is_(None),
        ).update(
            {"deleted_at": revoked_at, "is_read": True},
            synchronize_session=False,
        )
        db.commit()
        db.refresh(row)
        return _out(row)
