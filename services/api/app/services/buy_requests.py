from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Text, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.buy_request_schemas import (
    BuyRequestContactIn,
    BuyRequestCreateIn,
    BuyRequestUpdateIn,
    CloudComputeRequestDetailIn,
)
from app.config import settings
from app.domain.commerce import BUY_REQUEST_TRANSITIONS, can_transition
from app.models import (
    BuyRequest,
    BuyRequestContact,
    BuyRequestEvent,
    BuyRequestQuote,
    CloudComputeRequestDetail,
    User,
)
from app.security import ApiError


OPEN_REQUEST_STATUSES = ("draft", "reviewing", "published", "negotiating")
PUBLIC_REQUEST_STATUSES = ("published", "negotiating")
NON_NULL_UPDATE_FIELDS = {
    "request_type",
    "title",
    "visibility",
    "gpu_model",
    "gpu_quantity",
    "region_codes",
    "delivery_mode",
    "budget_currency",
    "budget_unit",
    "quote_deadline_at",
    "requirements",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError("TIMEZONE_REQUIRED", "时间必须包含时区", 422)
    return value.astimezone(timezone.utc)


def _stored_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _future_deadline(value: datetime, *, after: datetime | None = None) -> datetime:
    deadline = _aware(value)
    minimum = after or _now()
    if deadline <= minimum:
        raise ApiError("QUOTE_DEADLINE_INVALID", "报价截止时间必须晚于当前时间", 422)
    return deadline


def _request_number() -> str:
    return f"BR{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _money(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _detail_out(detail: CloudComputeRequestDetail | None) -> dict | None:
    if detail is None:
        return None
    return {
        "min_cpu_cores": detail.min_cpu_cores,
        "min_ram_gb": detail.min_ram_gb,
        "min_disk_gb": detail.min_disk_gb,
        "min_download_mbps": detail.min_download_mbps,
        "public_ip_required": detail.public_ip_required,
        "container_image": detail.container_image,
        "software_stack": detail.software_stack or [],
        "special_requirements": detail.special_requirements,
    }


def _contact_out(contact: BuyRequestContact | None) -> dict | None:
    if contact is None:
        return None
    return {
        "contact_name": contact.contact_name,
        "visible_after": contact.visible_after,
        "phone_configured": bool(contact.contact_phone_encrypted),
        "email_configured": bool(contact.contact_email_encrypted),
        "wechat_configured": bool(contact.contact_wechat_encrypted),
        "address_configured": bool(contact.address_encrypted),
    }


def _event_out(event: BuyRequestEvent) -> dict:
    return {
        "event_type": event.event_type,
        "actor_role": event.actor_role,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "payload": event.payload or {},
        "created_at": event.created_at,
    }


def request_out(
    row: BuyRequest,
    *,
    private: bool,
    detail: CloudComputeRequestDetail | None = None,
    contact: BuyRequestContact | None = None,
    events: list[BuyRequestEvent] | None = None,
) -> dict:
    data = {
        "request_no": row.request_no,
        "request_type": row.request_type,
        "title": row.title,
        "status": row.status,
        "visibility": row.visibility,
        "gpu_model": row.gpu_model,
        "min_gpu_memory_gb": row.min_gpu_memory_gb,
        "gpu_quantity": row.gpu_quantity,
        "region_codes": row.region_codes or [],
        "delivery_mode": row.delivery_mode,
        "budget": {
            "amount": _money(row.budget_amount),
            "currency": row.budget_currency,
            "unit": row.budget_unit,
        },
        "quote_deadline_at": row.quote_deadline_at,
        "expected_start_at": row.expected_start_at,
        "expected_duration_hours": row.expected_duration_hours,
        "requirements": row.requirements,
        "published_at": row.published_at,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if detail is not None:
        data["cloud_details"] = _detail_out(detail)
    if private:
        data.update({
            "id": row.id,
            "version": row.version,
            "closed_at": row.closed_at,
            "close_reason": row.close_reason,
        })
        data["contact"] = _contact_out(contact)
        if events is not None:
            data["events"] = [_event_out(event) for event in events]
    return data


def _reject_offline_request(request_type: str) -> None:
    if request_type != "cloud_compute":
        raise ApiError("OFFLINE_REQUEST_NOT_AVAILABLE", "线下设备求购尚未开放", 409)


def _reject_unencrypted_contact(contact: BuyRequestContactIn | None) -> None:
    if contact and any((contact.contact_phone, contact.contact_email, contact.contact_wechat, contact.address)):
        raise ApiError(
            "CONTACT_ENCRYPTION_UNAVAILABLE",
            "联系人敏感信息加密服务尚未配置，请暂时只填写联系人称呼",
            503,
        )


def _owned_request(db: Session, user: User, request_id: int, *, lock: bool = False) -> BuyRequest:
    query = db.query(BuyRequest).filter(BuyRequest.id == request_id, BuyRequest.buyer_id == user.id)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("BUY_REQUEST_NOT_FOUND", "求购不存在", 404)
    return row


def _check_version(row: BuyRequest, version: int) -> None:
    if row.version != version:
        raise ApiError("BUY_REQUEST_VERSION_CONFLICT", "求购已被更新，请刷新后重试", 409)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError("BUY_REQUEST_CONFLICT", "求购数据发生冲突，请刷新后重试", 409) from exc


def _put_detail(
    db: Session,
    request_id: int,
    data: CloudComputeRequestDetailIn | None,
) -> CloudComputeRequestDetail:
    row = db.get(CloudComputeRequestDetail, request_id)
    values = (data or CloudComputeRequestDetailIn()).model_dump()
    if row is None:
        row = CloudComputeRequestDetail(buy_request_id=request_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    return row


def _put_contact(
    db: Session,
    request_id: int,
    data: BuyRequestContactIn | None,
) -> BuyRequestContact | None:
    row = db.get(BuyRequestContact, request_id)
    if data is None:
        if row is not None:
            db.delete(row)
        return None
    _reject_unencrypted_contact(data)
    if row is None:
        row = BuyRequestContact(
            buy_request_id=request_id,
            contact_name=data.contact_name,
            visible_after=data.visible_after,
        )
        db.add(row)
    else:
        row.contact_name = data.contact_name
        row.visible_after = data.visible_after
    return row


def create_request(db: Session, user: User, data: BuyRequestCreateIn) -> BuyRequest:
    _reject_offline_request(data.request_type)
    _reject_unencrypted_contact(data.contact)
    deadline = _future_deadline(data.quote_deadline_at)
    expected_start = _aware(data.expected_start_at) if data.expected_start_at else None
    row = BuyRequest(
        request_no=_request_number(),
        buyer_id=user.id,
        request_type=data.request_type,
        title=data.title,
        status="draft",
        visibility=data.visibility,
        gpu_model=data.gpu_model,
        min_gpu_memory_gb=data.min_gpu_memory_gb,
        gpu_quantity=data.gpu_quantity,
        region_codes=list(dict.fromkeys(data.region_codes)),
        delivery_mode=data.delivery_mode,
        budget_amount=data.budget_amount,
        budget_currency=data.budget_currency,
        budget_unit=data.budget_unit,
        quote_deadline_at=deadline,
        expected_start_at=expected_start,
        expected_duration_hours=data.expected_duration_hours,
        requirements=data.requirements,
        version=1,
    )
    db.add(row)
    db.flush()
    _put_detail(db, row.id, data.cloud_details)
    _put_contact(db, row.id, data.contact)
    _commit(db)
    db.refresh(row)
    return row


def get_owned_request(db: Session, user: User, request_id: int) -> tuple:
    row = _owned_request(db, user, request_id)
    detail = db.get(CloudComputeRequestDetail, row.id)
    contact = db.get(BuyRequestContact, row.id)
    events = db.query(BuyRequestEvent).filter(
        BuyRequestEvent.buy_request_id == row.id
    ).order_by(BuyRequestEvent.created_at.asc(), BuyRequestEvent.id.asc()).all()
    return row, detail, contact, events


def list_owned_requests(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: str | None,
) -> tuple[list[BuyRequest], int]:
    query = db.query(BuyRequest).filter(BuyRequest.buyer_id == user.id)
    if status:
        query = query.filter(BuyRequest.status == status)
    total = query.count()
    rows = query.order_by(BuyRequest.created_at.desc(), BuyRequest.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return rows, total


def update_request(db: Session, user: User, request_id: int, data: BuyRequestUpdateIn) -> BuyRequest:
    _reject_unencrypted_contact(data.contact if "contact" in data.model_fields_set else None)
    row = _owned_request(db, user, request_id, lock=True)
    _check_version(row, data.version)
    if row.status != "draft":
        raise ApiError("BUY_REQUEST_NOT_EDITABLE", "只有草稿求购可以修改", 409)

    scalar_changes = data.model_dump(
        exclude_unset=True,
        exclude={"version", "cloud_details", "contact"},
    )
    for field in NON_NULL_UPDATE_FIELDS:
        if field in scalar_changes and scalar_changes[field] is None:
            raise ApiError("BUY_REQUEST_FIELD_REQUIRED", f"字段 {field} 不能为空", 422)
    if "request_type" in scalar_changes:
        _reject_offline_request(scalar_changes["request_type"])
    if "quote_deadline_at" in scalar_changes:
        scalar_changes["quote_deadline_at"] = _future_deadline(scalar_changes["quote_deadline_at"])
    if scalar_changes.get("expected_start_at") is not None:
        scalar_changes["expected_start_at"] = _aware(scalar_changes["expected_start_at"])
    if "region_codes" in scalar_changes:
        scalar_changes["region_codes"] = list(dict.fromkeys(scalar_changes["region_codes"]))
    for key, value in scalar_changes.items():
        setattr(row, key, value)
    if _stored_aware(row.quote_deadline_at) <= _now():
        raise ApiError("QUOTE_DEADLINE_INVALID", "报价截止时间必须晚于当前时间", 422)

    if "cloud_details" in data.model_fields_set:
        _put_detail(db, row.id, data.cloud_details)
    if "contact" in data.model_fields_set:
        _put_contact(db, row.id, data.contact)
    row.version += 1
    _commit(db)
    db.refresh(row)
    return row


def delete_request(db: Session, user: User, request_id: int, version: int) -> None:
    row = _owned_request(db, user, request_id, lock=True)
    _check_version(row, version)
    if row.status != "draft":
        raise ApiError("BUY_REQUEST_NOT_DELETABLE", "只有草稿求购可以删除", 409)
    if db.query(BuyRequestQuote.id).filter(BuyRequestQuote.buy_request_id == row.id).first():
        raise ApiError("BUY_REQUEST_NOT_DELETABLE", "已有报价的求购不能删除", 409)
    db.query(BuyRequestEvent).filter(BuyRequestEvent.buy_request_id == row.id).delete(
        synchronize_session=False
    )
    detail = db.get(CloudComputeRequestDetail, row.id)
    contact = db.get(BuyRequestContact, row.id)
    if detail is not None:
        db.delete(detail)
    if contact is not None:
        db.delete(contact)
    db.delete(row)
    _commit(db)


def _add_event(
    db: Session,
    row: BuyRequest,
    user: User,
    *,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    payload: dict | None = None,
) -> None:
    db.add(BuyRequestEvent(
        buy_request_id=row.id,
        actor_user_id=user.id,
        actor_role=user.role,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        payload=payload or {},
    ))


def publish_request(db: Session, user: User, request_id: int, version: int) -> BuyRequest:
    row = _owned_request(db, user, request_id, lock=True)
    _check_version(row, version)
    if row.status != "draft":
        raise ApiError("BUY_REQUEST_NOT_PUBLISHABLE", "只有草稿求购可以发布", 409)
    _reject_offline_request(row.request_type)
    deadline = _stored_aware(row.quote_deadline_at)
    if deadline <= _now():
        raise ApiError("QUOTE_DEADLINE_INVALID", "报价截止时间必须晚于当前时间", 422)
    target = "reviewing" if settings.BUY_REQUEST_REVIEW_ENABLED else "published"
    if not can_transition(BUY_REQUEST_TRANSITIONS, row.status, target):
        raise ApiError("BUY_REQUEST_TRANSITION_INVALID", "当前状态不能发布", 409)
    previous = row.status
    row.status = target
    row.version += 1
    if target == "published":
        row.published_at = _now()
        row.expires_at = deadline
    _add_event(
        db,
        row,
        user,
        event_type="submitted_for_review" if target == "reviewing" else "published",
        from_status=previous,
        to_status=target,
    )
    _commit(db)
    db.refresh(row)
    return row


def close_request(
    db: Session,
    user: User,
    request_id: int,
    *,
    version: int,
    reason: str,
) -> BuyRequest:
    row = _owned_request(db, user, request_id, lock=True)
    _check_version(row, version)
    if not can_transition(BUY_REQUEST_TRANSITIONS, row.status, "closed"):
        raise ApiError("BUY_REQUEST_NOT_CLOSABLE", "当前状态不能关闭求购", 409)
    previous = row.status
    row.status = "closed"
    row.closed_at = _now()
    row.close_reason = reason
    row.version += 1
    _add_event(
        db,
        row,
        user,
        event_type="closed",
        from_status=previous,
        to_status="closed",
        payload={"reason": reason},
    )
    _commit(db)
    db.refresh(row)
    return row


def extend_request(
    db: Session,
    user: User,
    request_id: int,
    *,
    version: int,
    quote_deadline_at: datetime,
) -> BuyRequest:
    row = _owned_request(db, user, request_id, lock=True)
    _check_version(row, version)
    if row.status not in PUBLIC_REQUEST_STATUSES:
        raise ApiError("BUY_REQUEST_NOT_EXTENDABLE", "当前状态不能延长报价期限", 409)
    deadline = _future_deadline(quote_deadline_at, after=_stored_aware(row.quote_deadline_at))
    previous_deadline = row.quote_deadline_at
    row.quote_deadline_at = deadline
    row.expires_at = deadline
    row.version += 1
    _add_event(
        db,
        row,
        user,
        event_type="deadline_extended",
        from_status=row.status,
        to_status=row.status,
        payload={
            "previous_quote_deadline_at": _stored_aware(previous_deadline).isoformat(),
            "quote_deadline_at": deadline.isoformat(),
        },
    )
    _commit(db)
    db.refresh(row)
    return row


def list_public_requests(
    db: Session,
    *,
    page: int,
    page_size: int,
    gpu_model: str | None,
    region: str | None,
    min_quantity: int | None,
    max_budget: Decimal | None,
    currency: str | None,
    status: str | None,
    sort: str,
) -> tuple[list[BuyRequest], int]:
    now = _now()
    query = db.query(BuyRequest).filter(
        BuyRequest.status.in_(PUBLIC_REQUEST_STATUSES),
        BuyRequest.visibility == "public",
        BuyRequest.quote_deadline_at > now,
        or_(BuyRequest.expires_at.is_(None), BuyRequest.expires_at > now),
    )
    if status:
        query = query.filter(BuyRequest.status == status)
    if gpu_model:
        query = query.filter(BuyRequest.gpu_model.ilike(f"%{gpu_model.strip()}%"))
    if region:
        query = query.filter(cast(BuyRequest.region_codes, Text).like(f'%"{region.strip()}"%'))
    if min_quantity is not None:
        query = query.filter(BuyRequest.gpu_quantity >= min_quantity)
    if max_budget is not None:
        if not currency:
            raise ApiError("BUDGET_CURRENCY_REQUIRED", "按预算筛选时必须指定币种", 422)
        query = query.filter(
            BuyRequest.budget_currency == currency,
            BuyRequest.budget_amount.isnot(None),
            BuyRequest.budget_amount <= max_budget,
        )
    elif currency:
        query = query.filter(BuyRequest.budget_currency == currency)
    total = query.count()
    if sort == "deadline":
        order = (BuyRequest.quote_deadline_at.asc(), BuyRequest.id.desc())
    elif sort == "budget":
        order = (
            BuyRequest.budget_amount.is_(None),
            BuyRequest.budget_amount.asc(),
            BuyRequest.id.desc(),
        )
    else:
        order = (func.coalesce(BuyRequest.published_at, BuyRequest.created_at).desc(), BuyRequest.id.desc())
    rows = query.order_by(*order).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def get_public_request(db: Session, request_no: str) -> tuple[BuyRequest, CloudComputeRequestDetail | None]:
    now = _now()
    row = db.query(BuyRequest).filter(
        BuyRequest.request_no == request_no,
        BuyRequest.status.in_(PUBLIC_REQUEST_STATUSES),
        BuyRequest.visibility == "public",
        BuyRequest.quote_deadline_at > now,
        or_(BuyRequest.expires_at.is_(None), BuyRequest.expires_at > now),
    ).first()
    if row is None:
        raise ApiError("BUY_REQUEST_NOT_FOUND", "求购不存在或尚未公开", 404)
    return row, db.get(CloudComputeRequestDetail, row.id)
