from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
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
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/notifications", tags=["notification"])


def _serialize_notification(notification: Notification) -> dict:
    return NotificationOut.model_validate(notification).model_dump()


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
    # Existing closed-test accounts receive one factual service-state message,
    # so the inbox works without fabricated order or revenue records.
    ensure_inbox_welcome(db, user.id)
    db.commit()

    query = db.query(Notification).filter(Notification.user_id == user.id)
    if type_filter:
        query = query.filter(Notification.type == type_filter)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    total = query.count()
    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    unread = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).count()
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
    unread = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).count()
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
    changed = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return success({"unread": 0, "changed": changed})


@router.post("/{nid}/read")
def mark_read(
    nid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(
        Notification.id == nid,
        Notification.user_id == user.id,
    ).first()
    if not notification:
        raise BizError("通知不存在", status_code=404)
    if not notification.is_read:
        notification.is_read = True
        db.commit()
    return success({"id": nid, "is_read": True})
