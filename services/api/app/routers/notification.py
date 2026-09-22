from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    MajorAnnouncementOut,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)
from app.services.notification_service import (
    VALID_NOTIFICATION_TYPES,
    ensure_inbox_welcome,
    get_or_create_preferences,
    push_delivery_status,
)
from app.services.notification_broadcast import latest_major_announcement
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/notifications", tags=["notification"])


def _serialize_notification(notification: Notification) -> dict:
    return NotificationOut.model_validate(notification).model_dump()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _visible_notifications(query):
    now = _utcnow()
    return query.filter(
        Notification.deleted_at.is_(None),
        or_(Notification.expires_at.is_(None), Notification.expires_at > now),
    )


@router.get("/major-announcement")
def get_major_announcement(
    db: Session = Depends(get_db),
):
    """Latest completed major notice for the public home surfaces.

    Administrator identity and recipient counts intentionally stay private;
    the same announcement is also delivered to each active account's inbox.
    """

    row = latest_major_announcement(db)
    return success(MajorAnnouncementOut.model_validate(row).model_dump() if row else None)


@router.get("")
def list_notifications(
    type_filter: str | None = None,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if type_filter and type_filter not in VALID_NOTIFICATION_TYPES:
        raise BizError("不支持的通知类型")
    # Existing accounts receive one factual service-state message,
    # so the inbox works without fabricated order or revenue records.
    ensure_inbox_welcome(db, user.id)
    db.commit()

    query = _visible_notifications(
        db.query(Notification).filter(Notification.user_id == user.id)
    )
    if type_filter:
        query = query.filter(Notification.type == type_filter)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    total = query.count()
    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    unread = _visible_notifications(db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    )).count()
    return success({
        "items": [_serialize_notification(item) for item in items],
        "unread": unread,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    })


@router.get("/unread-count")
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_inbox_welcome(db, user.id)
    db.commit()
    unread = _visible_notifications(db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    )).count()
    return success({"unread": unread})


@router.get("/preferences")
def get_preferences(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preferences = get_or_create_preferences(db, user.id)
    db.commit()
    db.refresh(preferences)
    return success({
        "preferences": NotificationPreferenceOut.model_validate(preferences).model_dump(),
        "delivery": push_delivery_status(),
    })


@router.put("/preferences")
def update_preferences(
    data: NotificationPreferenceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preferences = get_or_create_preferences(db, user.id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(preferences, field, value)
    db.commit()
    db.refresh(preferences)
    return success({
        "preferences": NotificationPreferenceOut.model_validate(preferences).model_dump(),
        "delivery": push_delivery_status(),
    })


@router.post("/read-all")
def mark_all_read(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    changed = _visible_notifications(db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    )).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return success({"unread": 0, "changed": changed})


@router.post("/{nid}/read")
def mark_read(
    nid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = _visible_notifications(db.query(Notification).filter(
        Notification.id == nid,
        Notification.user_id == user.id,
    )).first()
    if not notification:
        raise BizError("通知不存在", status_code=404)
    if not notification.is_read:
        notification.is_read = True
        db.commit()
    return success({"id": nid, "is_read": True})


@router.delete("/{nid}")
def delete_notification(
    nid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hide one notification only from the authenticated account's inbox."""

    notification = db.query(Notification).filter(
        Notification.id == nid,
        Notification.user_id == user.id,
    ).first()
    if not notification:
        raise BizError("通知不存在", status_code=404)
    if notification.deleted_at is None:
        notification.deleted_at = _utcnow()
        notification.is_read = True
        db.commit()
    return success({"id": nid, "deleted": True})
