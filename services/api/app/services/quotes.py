from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.commerce import (
    BUY_REQUEST_TRANSITIONS,
    QUOTE_TRANSITIONS,
    can_transition,
)
from app.models import (
    BuyRequest,
    BuyRequestEvent,
    BuyRequestQuote,
    CloudComputeRequestDetail,
    Order,
    OrderEvent,
    Product,
    SupplierApplication,
    User,
)
from app.quote_schemas import QuoteCreateIn, QuoteUpdateIn
from app.security import ApiError
from app.services import buy_requests as buy_request_service
from app.services import resources as resource_service


QUOTEABLE_REQUEST_STATUSES = ("published", "negotiating")
BUYER_VISIBLE_QUOTE_STATUSES = (
    "submitted",
    "shortlisted",
    "accepted",
    "rejected",
    "withdrawn",
    "expired",
)
ACTIVE_QUOTE_STATUSES = ("draft", "submitted", "shortlisted", "accepted")
NON_NULL_QUOTE_FIELDS = {
    "price_amount",
    "price_currency",
    "price_unit",
    "available_quantity",
    "valid_until",
    "service_description",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _input_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError("TIMEZONE_REQUIRED", "时间必须包含时区", 422)
    return value.astimezone(timezone.utc)


def _stored_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value: Decimal) -> str:
    return format(value, "f")


def _quote_number() -> str:
    return f"BQ{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _order_number() -> str:
    return f"WO{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _supplier_out(user: User, application: SupplierApplication | None) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "company_name": application.company_name if application else None,
    }


def request_summary(row: BuyRequest) -> dict:
    return {
        "id": row.id,
        "request_no": row.request_no,
        "title": row.title,
        "status": row.status,
        "gpu_model": row.gpu_model,
        "gpu_quantity": row.gpu_quantity,
        "quote_deadline_at": row.quote_deadline_at,
    }


def quote_out(
    row: BuyRequestQuote,
    *,
    supplier: User | None = None,
    application: SupplierApplication | None = None,
    request: BuyRequest | None = None,
) -> dict:
    data = {
        "id": row.id,
        "quote_no": row.quote_no,
        "buy_request_id": row.buy_request_id,
        "resource_id": row.resource_id,
        "status": row.status,
        "price": {
            "amount": _money(row.price_amount),
            "currency": row.price_currency,
            "unit": row.price_unit,
        },
        "available_quantity": row.available_quantity,
        "delivery_time_hours": row.delivery_time_hours,
        "valid_until": row.valid_until,
        "is_expired": _stored_aware(row.valid_until) <= _now(),
        "service_description": row.service_description,
        "buyer_note": row.buyer_note,
        "submitted_at": row.submitted_at,
        "accepted_at": row.accepted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }
    if supplier is not None:
        data["supplier"] = _supplier_out(supplier, application)
    if request is not None:
        data["request"] = request_summary(request)
    return data


def order_out(row: Order) -> dict:
    return {
        "id": row.id,
        "order_no": row.order_no,
        "status": row.status,
        "buyer_id": row.buyer_id,
        "supplier_id": row.supplier_id,
        "buy_request_id": row.buy_request_id,
        "accepted_quote_id": row.accepted_quote_id,
        "product_id": row.product_id,
        "order_source": row.order_source,
        "environment": row.environment,
        "payment_status": row.payment_status,
        "duration_hours": row.duration_hours,
        "amount": _money(row.amount),
        "currency": row.currency,
        "price_unit": row.price_unit,
        "quantity": row.quantity,
        "snapshot": row.snapshot,
        "buyer_confirmed_at": row.buyer_confirmed_at,
        "supplier_confirmed_at": row.supplier_confirmed_at,
        "confirmed_at": row.confirmed_at,
        "delivery_started_at": row.delivery_started_at,
        "delivered_at": row.delivered_at,
        "completed_at": row.completed_at,
        "cancelled_at": row.cancelled_at,
        "cancel_reason": row.cancel_reason,
        "delivery_note": row.delivery_note,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def require_approved_supplier(db: Session, user: User) -> SupplierApplication:
    application = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == user.id
    ).first()
    if user.role != "supplier" or application is None or application.status != "approved":
        raise ApiError("SUPPLIER_APPROVAL_REQUIRED", "只有已审核通过的商家可以报价", 403)
    return application


def _commit(
    db: Session,
    *,
    code: str = "QUOTE_CONFLICT",
    message: str = "报价数据发生冲突，请刷新后重试",
) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(code, message, 409) from exc


def _request_by_id(db: Session, request_id: int, *, lock: bool = False) -> BuyRequest:
    query = db.query(BuyRequest).filter(BuyRequest.id == request_id)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("BUY_REQUEST_NOT_FOUND", "求购不存在", 404)
    return row


def _owned_buyer_request(
    db: Session,
    user: User,
    request_id: int,
    *,
    lock: bool = False,
) -> BuyRequest:
    query = db.query(BuyRequest).filter(
        BuyRequest.id == request_id,
        BuyRequest.buyer_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("BUY_REQUEST_NOT_FOUND", "求购不存在", 404)
    return row


def _ensure_quoteable_request(row: BuyRequest, user: User | None = None) -> None:
    if row.visibility != "public":
        raise ApiError("BUY_REQUEST_NOT_FOUND", "求购不存在或尚未公开", 404)
    if user is not None and row.buyer_id == user.id:
        raise ApiError("SUPPLIER_CANNOT_QUOTE_OWN_REQUEST", "不能对自己发布的求购报价", 409)
    if row.status not in QUOTEABLE_REQUEST_STATUSES:
        raise ApiError("BUY_REQUEST_NOT_QUOTEABLE", "当前求购不能接收报价", 409)
    if _stored_aware(row.quote_deadline_at) <= _now():
        raise ApiError("BUY_REQUEST_QUOTE_DEADLINE_PASSED", "求购报价截止时间已过", 409)


def _check_version(row: BuyRequestQuote, version: int) -> None:
    if row.version != version:
        raise ApiError("QUOTE_VERSION_CONFLICT", "报价已被更新，请刷新后重试", 409)


def _check_request_version(row: BuyRequest, version: int) -> None:
    if row.version != version:
        raise ApiError("BUY_REQUEST_VERSION_CONFLICT", "求购已被更新，请刷新后重试", 409)


def _owned_supplier_quote(
    db: Session,
    user: User,
    quote_id: int,
    *,
    lock: bool = False,
) -> BuyRequestQuote:
    query = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.supplier_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("QUOTE_NOT_FOUND", "报价不存在", 404)
    return row


def _supplier_quote_context(
    db: Session,
    user: User,
    quote_id: int,
) -> tuple[BuyRequest, BuyRequestQuote]:
    preview = _owned_supplier_quote(db, user, quote_id)
    request = _request_by_id(db, preview.buy_request_id, lock=True)
    quote = _owned_supplier_quote(db, user, quote_id, lock=True)
    return request, quote


def _buyer_quote(
    db: Session,
    request_id: int,
    quote_id: int,
    *,
    lock: bool = False,
) -> BuyRequestQuote:
    query = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.buy_request_id == request_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None or row.status == "draft":
        raise ApiError("QUOTE_NOT_FOUND", "报价不存在", 404)
    return row


def _resource_for_quote(
    db: Session,
    supplier: User,
    resource_id: int | None,
    quantity: int,
    gpu_model: str,
) -> Product | None:
    if resource_id is None:
        return None
    return resource_service.ensure_quote_resource(
        db, supplier, resource_id, quantity, gpu_model
    )


def _validate_quote_values(
    db: Session,
    request: BuyRequest,
    supplier: User,
    *,
    price_currency: str,
    price_unit: str,
    available_quantity: int,
    valid_until: datetime,
    resource_id: int | None,
    input_datetime: bool,
) -> datetime:
    _ensure_quoteable_request(request, supplier)
    valid = _input_aware(valid_until) if input_datetime else _stored_aware(valid_until)
    if valid <= _now():
        raise ApiError("QUOTE_VALID_UNTIL_INVALID", "报价有效期必须晚于当前时间", 422)
    if valid > _stored_aware(request.quote_deadline_at):
        raise ApiError("QUOTE_VALID_UNTIL_INVALID", "报价有效期不能晚于求购截止时间", 422)
    if price_currency != request.budget_currency or price_unit != request.budget_unit:
        raise ApiError("QUOTE_PRICE_UNIT_MISMATCH", "报价币种和计价单位必须与求购一致", 409)
    if available_quantity < request.gpu_quantity:
        raise ApiError("QUOTE_QUANTITY_INSUFFICIENT", "P0 暂不支持拆单，报价数量不能少于求购数量", 409)
    _resource_for_quote(
        db,
        supplier,
        resource_id,
        available_quantity,
        request.gpu_model,
    )
    return valid


def _add_request_event(
    db: Session,
    request: BuyRequest,
    actor: User,
    *,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(BuyRequestEvent(
        buy_request_id=request.id,
        actor_user_id=actor.id,
        actor_role=actor.role,
        event_type=event_type,
        from_status=from_status if from_status is not None else request.status,
        to_status=to_status if to_status is not None else request.status,
        payload=payload or {},
    ))


def get_supplier_request(
    db: Session,
    user: User,
    request_id: int,
) -> tuple[BuyRequest, CloudComputeRequestDetail | None, list[BuyRequestQuote]]:
    require_approved_supplier(db, user)
    request = _request_by_id(db, request_id)
    _ensure_quoteable_request(request, user)
    detail = db.get(CloudComputeRequestDetail, request.id)
    quotes = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == request.id,
        BuyRequestQuote.supplier_id == user.id,
    ).order_by(BuyRequestQuote.created_at.desc(), BuyRequestQuote.id.desc()).all()
    return request, detail, quotes


def list_supplier_requests(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    gpu_model: str | None,
    region: str | None,
    status: str | None,
    sort: str,
) -> tuple[list[BuyRequest], int]:
    """Return quoteable requests with the internal id required by supplier actions."""
    require_approved_supplier(db, user)
    return buy_request_service.list_public_requests(
        db,
        page=page,
        page_size=page_size,
        gpu_model=gpu_model,
        region=region,
        min_quantity=None,
        max_budget=None,
        currency=None,
        status=status,
        sort=sort,
    )


def supplier_request_summary_out(request: BuyRequest) -> dict:
    return {
        "id": request.id,
        **buy_request_service.request_out(request, private=False),
    }


def create_quote(
    db: Session,
    user: User,
    request_id: int,
    data: QuoteCreateIn,
) -> BuyRequestQuote:
    require_approved_supplier(db, user)
    request = _request_by_id(db, request_id, lock=True)
    valid_until = _validate_quote_values(
        db,
        request,
        user,
        price_currency=data.price_currency,
        price_unit=data.price_unit,
        available_quantity=data.available_quantity,
        valid_until=data.valid_until,
        resource_id=data.resource_id,
        input_datetime=True,
    )
    active = db.query(BuyRequestQuote.id).filter(
        BuyRequestQuote.buy_request_id == request.id,
        BuyRequestQuote.supplier_id == user.id,
        BuyRequestQuote.status.in_(ACTIVE_QUOTE_STATUSES),
    ).first()
    if active:
        raise ApiError("ACTIVE_QUOTE_EXISTS", "该求购已有活动报价", 409)
    row = BuyRequestQuote(
        quote_no=_quote_number(),
        buy_request_id=request.id,
        supplier_id=user.id,
        resource_id=data.resource_id,
        status="draft",
        price_amount=data.price_amount,
        price_currency=data.price_currency,
        price_unit=data.price_unit,
        available_quantity=data.available_quantity,
        delivery_time_hours=data.delivery_time_hours,
        valid_until=valid_until,
        service_description=data.service_description,
        version=1,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError("ACTIVE_QUOTE_EXISTS", "该求购已有活动报价", 409) from exc
    _commit(db)
    db.refresh(row)
    return row


def list_supplier_quotes(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: str | None,
) -> tuple[list[tuple[BuyRequestQuote, BuyRequest]], int]:
    require_approved_supplier(db, user)
    query = db.query(BuyRequestQuote).filter(BuyRequestQuote.supplier_id == user.id)
    if status:
        query = query.filter(BuyRequestQuote.status == status)
    total = query.count()
    quotes = query.order_by(
        BuyRequestQuote.created_at.desc(), BuyRequestQuote.id.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    rows = [(quote, _request_by_id(db, quote.buy_request_id)) for quote in quotes]
    return rows, total


def get_supplier_quote(
    db: Session,
    user: User,
    quote_id: int,
) -> tuple[BuyRequestQuote, BuyRequest]:
    require_approved_supplier(db, user)
    quote = _owned_supplier_quote(db, user, quote_id)
    return quote, _request_by_id(db, quote.buy_request_id)


def update_quote(
    db: Session,
    user: User,
    quote_id: int,
    data: QuoteUpdateIn,
) -> BuyRequestQuote:
    require_approved_supplier(db, user)
    request, quote = _supplier_quote_context(db, user, quote_id)
    _check_version(quote, data.version)
    if quote.status != "draft":
        raise ApiError("QUOTE_NOT_EDITABLE", "只有草稿报价可以修改", 409)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if not changes:
        raise ApiError("QUOTE_UPDATE_EMPTY", "至少需要修改一个报价字段", 422)
    for field in NON_NULL_QUOTE_FIELDS:
        if field in changes and changes[field] is None:
            raise ApiError("QUOTE_FIELD_REQUIRED", f"字段 {field} 不能为空", 422)
    if changes.get("valid_until") is not None:
        changes["valid_until"] = _input_aware(changes["valid_until"])
    for key, value in changes.items():
        setattr(quote, key, value)
    quote.valid_until = _validate_quote_values(
        db,
        request,
        user,
        price_currency=quote.price_currency,
        price_unit=quote.price_unit,
        available_quantity=quote.available_quantity,
        valid_until=quote.valid_until,
        resource_id=quote.resource_id,
        input_datetime=False,
    )
    quote.version += 1
    _commit(db)
    db.refresh(quote)
    return quote


def submit_quote(
    db: Session,
    user: User,
    quote_id: int,
    version: int,
) -> BuyRequestQuote:
    require_approved_supplier(db, user)
    request, quote = _supplier_quote_context(db, user, quote_id)
    _check_version(quote, version)
    if not can_transition(QUOTE_TRANSITIONS, quote.status, "submitted"):
        raise ApiError("QUOTE_NOT_SUBMITTABLE", "当前报价不能提交", 409)
    quote.valid_until = _validate_quote_values(
        db,
        request,
        user,
        price_currency=quote.price_currency,
        price_unit=quote.price_unit,
        available_quantity=quote.available_quantity,
        valid_until=quote.valid_until,
        resource_id=quote.resource_id,
        input_datetime=False,
    )
    previous_request_status = request.status
    if request.status == "published":
        if not can_transition(BUY_REQUEST_TRANSITIONS, request.status, "negotiating"):
            raise ApiError("BUY_REQUEST_TRANSITION_INVALID", "求购当前不能进入议价状态", 409)
        request.status = "negotiating"
    request.version += 1
    quote.status = "submitted"
    quote.submitted_at = _now()
    quote.version += 1
    _add_request_event(
        db,
        request,
        user,
        event_type="quote_submitted",
        from_status=previous_request_status,
        to_status=request.status,
        payload={"quote_id": quote.id, "quote_no": quote.quote_no},
    )
    _commit(db)
    db.refresh(quote)
    return quote


def withdraw_quote(
    db: Session,
    user: User,
    quote_id: int,
    *,
    version: int,
    reason: str | None,
) -> BuyRequestQuote:
    require_approved_supplier(db, user)
    request, quote = _supplier_quote_context(db, user, quote_id)
    _check_version(quote, version)
    if not can_transition(QUOTE_TRANSITIONS, quote.status, "withdrawn"):
        raise ApiError("QUOTE_NOT_WITHDRAWABLE", "当前报价不能撤回", 409)
    previous = quote.status
    quote.status = "withdrawn"
    quote.version += 1
    if previous != "draft":
        _add_request_event(
            db,
            request,
            user,
            event_type="quote_withdrawn",
            payload={
                "quote_id": quote.id,
                "quote_no": quote.quote_no,
                "quote_from_status": previous,
                "quote_to_status": "withdrawn",
                "reason": reason,
            },
        )
    _commit(db)
    db.refresh(quote)
    return quote


def list_buyer_quotes(
    db: Session,
    user: User,
    request_id: int,
    *,
    page: int,
    page_size: int,
    status: str | None,
) -> tuple[BuyRequest, list[tuple[BuyRequestQuote, User, SupplierApplication | None]], int]:
    request = _owned_buyer_request(db, user, request_id)
    query = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == request.id,
        BuyRequestQuote.status.in_(BUYER_VISIBLE_QUOTE_STATUSES),
    )
    if status:
        query = query.filter(BuyRequestQuote.status == status)
    total = query.count()
    quotes = query.order_by(
        BuyRequestQuote.created_at.desc(), BuyRequestQuote.id.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    rows = []
    for quote in quotes:
        supplier = db.get(User, quote.supplier_id)
        application = db.query(SupplierApplication).filter(
            SupplierApplication.user_id == quote.supplier_id
        ).first()
        rows.append((quote, supplier, application))
    return request, rows, total


def shortlist_quote(
    db: Session,
    user: User,
    request_id: int,
    quote_id: int,
    *,
    quote_version: int,
    note: str | None,
) -> BuyRequestQuote:
    request = _owned_buyer_request(db, user, request_id, lock=True)
    if request.status != "negotiating":
        raise ApiError("BUY_REQUEST_NOT_NEGOTIATING", "当前求购不在议价状态", 409)
    quote = _buyer_quote(db, request.id, quote_id, lock=True)
    _check_version(quote, quote_version)
    if not can_transition(QUOTE_TRANSITIONS, quote.status, "shortlisted"):
        raise ApiError("QUOTE_NOT_SHORTLISTABLE", "当前报价不能入围", 409)
    if _stored_aware(quote.valid_until) <= _now():
        raise ApiError("QUOTE_EXPIRED", "报价已过期", 409)
    quote.status = "shortlisted"
    quote.buyer_note = note
    quote.version += 1
    _add_request_event(
        db,
        request,
        user,
        event_type="quote_shortlisted",
        payload={"quote_id": quote.id, "quote_no": quote.quote_no, "note": note},
    )
    _commit(db)
    db.refresh(quote)
    return quote


def reject_quote(
    db: Session,
    user: User,
    request_id: int,
    quote_id: int,
    *,
    quote_version: int,
    note: str | None,
) -> BuyRequestQuote:
    request = _owned_buyer_request(db, user, request_id, lock=True)
    if request.status != "negotiating":
        raise ApiError("BUY_REQUEST_NOT_NEGOTIATING", "当前求购不在议价状态", 409)
    quote = _buyer_quote(db, request.id, quote_id, lock=True)
    _check_version(quote, quote_version)
    if not can_transition(QUOTE_TRANSITIONS, quote.status, "rejected"):
        raise ApiError("QUOTE_NOT_REJECTABLE", "当前报价不能拒绝", 409)
    previous = quote.status
    quote.status = "rejected"
    quote.buyer_note = note
    quote.version += 1
    _add_request_event(
        db,
        request,
        user,
        event_type="quote_rejected",
        payload={
            "quote_id": quote.id,
            "quote_no": quote.quote_no,
            "quote_from_status": previous,
            "quote_to_status": "rejected",
            "note": note,
        },
    )
    _commit(db)
    db.refresh(quote)
    return quote


def _snapshot(
    request: BuyRequest,
    quote: BuyRequestQuote,
    supplier: User,
    application: SupplierApplication,
) -> dict:
    return {
        "pricing_semantics": "quoted_unit_price",
        "request": {
            "request_no": request.request_no,
            "title": request.title,
            "request_type": request.request_type,
            "gpu_model": request.gpu_model,
            "gpu_quantity": request.gpu_quantity,
            "region_codes": request.region_codes or [],
            "delivery_mode": request.delivery_mode,
            "expected_start_at": (
                _stored_aware(request.expected_start_at).isoformat()
                if request.expected_start_at else None
            ),
            "expected_duration_hours": request.expected_duration_hours,
            "requirements": request.requirements,
        },
        "quote": {
            "quote_no": quote.quote_no,
            "resource_id": quote.resource_id,
            "price_amount": _money(quote.price_amount),
            "price_currency": quote.price_currency,
            "price_unit": quote.price_unit,
            "available_quantity": quote.available_quantity,
            "delivery_time_hours": quote.delivery_time_hours,
            "valid_until": _stored_aware(quote.valid_until).isoformat(),
            "service_description": quote.service_description,
        },
        "supplier": _supplier_out(supplier, application),
    }


def accept_quote(
    db: Session,
    user: User,
    request_id: int,
    quote_id: int,
    *,
    request_version: int,
    quote_version: int,
    note: str | None,
) -> tuple[Order, bool]:
    request = _owned_buyer_request(db, user, request_id, lock=True)
    existing = db.query(Order).filter(Order.buy_request_id == request.id).first()
    if existing is not None:
        if existing.accepted_quote_id != quote_id:
            raise ApiError("BUY_REQUEST_ALREADY_MATCHED", "该求购已经接受了其他报价", 409)
        return existing, True

    _check_request_version(request, request_version)
    if request.status != "negotiating" or not can_transition(
        BUY_REQUEST_TRANSITIONS, request.status, "matched"
    ):
        raise ApiError("BUY_REQUEST_NOT_MATCHABLE", "当前求购不能接受报价", 409)
    if _stored_aware(request.quote_deadline_at) <= _now():
        raise ApiError("BUY_REQUEST_QUOTE_DEADLINE_PASSED", "求购报价截止时间已过", 409)

    quote = _buyer_quote(db, request.id, quote_id, lock=True)
    _check_version(quote, quote_version)
    if not can_transition(QUOTE_TRANSITIONS, quote.status, "accepted"):
        raise ApiError("QUOTE_NOT_ACCEPTABLE", "报价必须先入围且处于可接受状态", 409)
    if _stored_aware(quote.valid_until) <= _now():
        raise ApiError("QUOTE_EXPIRED", "报价已过期", 409)

    supplier = db.query(User).filter(
        User.id == quote.supplier_id,
        User.status == "active",
    ).first()
    if supplier is None:
        raise ApiError("SUPPLIER_UNAVAILABLE", "报价商家账户当前不可用", 409)
    application = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == supplier.id,
        SupplierApplication.status == "approved",
    ).first()
    if supplier.role != "supplier" or application is None:
        raise ApiError("SUPPLIER_UNAVAILABLE", "报价商家资格当前不可用", 409)
    _validate_quote_values(
        db,
        request,
        supplier,
        price_currency=quote.price_currency,
        price_unit=quote.price_unit,
        available_quantity=quote.available_quantity,
        valid_until=quote.valid_until,
        resource_id=quote.resource_id,
        input_datetime=False,
    )

    previous_request_status = request.status
    request.status = "matched"
    request.version += 1
    quote.status = "accepted"
    quote.accepted_at = _now()
    quote.buyer_note = note
    quote.version += 1

    other_quotes = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == request.id,
        BuyRequestQuote.id != quote.id,
        BuyRequestQuote.status.in_(("draft", "submitted", "shortlisted")),
    ).with_for_update().all()
    rejected_quote_nos = []
    withdrawn_quote_nos = []
    for other in other_quotes:
        if other.status == "draft":
            other.status = "withdrawn"
            withdrawn_quote_nos.append(other.quote_no)
        else:
            other.status = "rejected"
            rejected_quote_nos.append(other.quote_no)
        other.version += 1

    accepted_at = _now()
    order = Order(
        order_no=_order_number(),
        buyer_id=request.buyer_id,
        supplier_id=quote.supplier_id,
        buy_request_id=request.id,
        accepted_quote_id=quote.id,
        status="pending_confirmation",
        amount=quote.price_amount,
        currency=quote.price_currency,
        price_unit=quote.price_unit,
        quantity=request.gpu_quantity,
        snapshot=_snapshot(request, quote, supplier, application),
        buyer_confirmed_at=accepted_at,
        version=1,
    )
    db.add(order)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(Order).filter(Order.buy_request_id == request_id).first()
        if existing is not None and existing.accepted_quote_id == quote_id:
            return existing, True
        if existing is not None:
            raise ApiError("BUY_REQUEST_ALREADY_MATCHED", "该求购已经接受了其他报价", 409)
        raise ApiError("ORDER_CONFLICT", "订单创建冲突，请刷新后重试", 409)

    if quote.resource_id is not None:
        resource_service.reserve_for_order(
            db,
            order,
            quote.resource_id,
            request.gpu_quantity,
        )

    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=user.id,
        actor_role=user.role,
        event_type="created_from_accepted_quote",
        from_status=None,
        to_status="pending_confirmation",
        payload={
            "buy_request_id": request.id,
            "accepted_quote_id": quote.id,
            "payment_required": False,
        },
    ))
    _add_request_event(
        db,
        request,
        user,
        event_type="quote_accepted",
        from_status=previous_request_status,
        to_status="matched",
        payload={
            "quote_id": quote.id,
            "quote_no": quote.quote_no,
            "order_id": order.id,
            "order_no": order.order_no,
            "rejected_quote_nos": rejected_quote_nos,
            "withdrawn_quote_nos": withdrawn_quote_nos,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Order).filter(Order.buy_request_id == request_id).first()
        if existing is not None and existing.accepted_quote_id == quote_id:
            return existing, True
        if existing is not None:
            raise ApiError("BUY_REQUEST_ALREADY_MATCHED", "该求购已经接受了其他报价", 409)
        raise ApiError("ORDER_CONFLICT", "订单创建冲突，请刷新后重试", 409)
    db.refresh(order)
    return order, False


def supplier_request_out(
    request: BuyRequest,
    detail: CloudComputeRequestDetail | None,
    quotes: list[BuyRequestQuote],
) -> dict:
    return {
        "request": buy_request_service.request_out(
            request,
            private=False,
            detail=detail,
        ),
        "own_quotes": [quote_out(quote, request=request) for quote in quotes],
    }
