from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.buy_request import (
    BuyRequest,
    BuyRequestDeal,
    BuyRequestQuote,
    BuyRequestQuoteRevision,
)
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.buy_request import (
    DealActionIn,
    DealReasonIn,
    DeliveryIssueIn,
    MatchmakingCredentialIn,
    QuoteRevisionIn,
)
from app.services import buy_request_matchmaking as matchmaking
from app.services.gpu_catalog import canonicalize_gpu
from app.services.trade_mode import (
    commerce_mode,
    direct_trade_enabled,
    require_matchmaking_enabled,
)
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/buy-requests", tags=["buy-request"])
admin_router = APIRouter(prefix="/api/admin/buy-requests", tags=["admin", "buy-request"])
OPEN_STATUSES = ("published", "quoting")
_MATCHMAKING_WRITE_CONFLICT_MESSAGE = "撮合状态正在更新，请刷新后重试"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_contact_phone(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 32 or not re.fullmatch(r"[+0-9 ()-]+", cleaned):
        return None
    normalized = re.sub(r"[ ()-]", "", cleaned)
    if not re.fullmatch(r"(?:[0-9]{6,20}|\+[1-9][0-9]{5,14})", normalized):
        return None
    return normalized


class BuyRequestIn(BaseModel):
    client_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    request_type: str
    gpu_model: str
    gpu_variant: str | None = None
    quantity: int = Field(default=1, ge=1, le=10000)
    gpu_hours: int | None = Field(default=None, ge=1)
    max_unit_price: float | None = Field(default=None, ge=0)
    budget: float | None = Field(default=None, ge=0)
    currency: str = "CNY"
    region: str | None = None
    billing_mode: str | None = None
    requirements: dict | None = None
    contact: str | None = None
    phone: str | None = Field(
        default=None,
        min_length=6,
        max_length=20,
        pattern=r"^(?:[0-9]{6,20}|\+[1-9][0-9]{5,14})$",
    )
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)

    @field_validator("phone", mode="before")
    @classmethod
    def clean_contact_phone(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            normalized = _normalize_contact_phone(value)
            if normalized is None:
                raise ValueError("invalid contact phone")
            return normalized
        return value


class QuoteIn(BaseModel):
    unit_price: float | None = Field(default=None, ge=0)
    total_price: float = Field(ge=0)
    currency: str = "CNY"
    available_at: datetime | None = None
    message: str | None = Field(default=None, max_length=1000)
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    if len(phone) < 7:
        return "****"
    return f"{phone[:3]}****{phone[-4:]}"


_PRIVATE_REQUIREMENT_KEYS = {
    "buyer", "buyer_name", "contact", "contact_name", "email", "mobile",
    "name", "phone", "qq", "real_name", "username", "wechat", "weixin",
}


def _public_requirements(value, private_tokens: tuple[str, ...]):
    """Remove identity/contact material from supplier-facing free-form JSON."""
    if isinstance(value, dict):
        return {
            key: _public_requirements(item, private_tokens)
            for key, item in value.items()
            if str(key).strip().lower() not in _PRIVATE_REQUIREMENT_KEYS
        }
    if isinstance(value, list):
        return [_public_requirements(item, private_tokens) for item in value]
    if isinstance(value, str):
        sanitized = value
        for token in private_tokens:
            if token:
                sanitized = sanitized.replace(token, "[已隐藏]")
        return sanitized
    return value


def _public_quote_message(value: str | None, supplier: Supplier | None) -> str | None:
    if not value:
        return value
    sanitized = value
    if supplier:
        for token in (supplier.contact, supplier.phone, _mask_phone(supplier.phone)):
            if token:
                sanitized = sanitized.replace(token, "[已隐藏]")
    sanitized = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已隐藏]", sanitized)
    sanitized = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[已隐藏]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def _expire_if_needed(item: BuyRequest, now: datetime) -> None:
    if item.status in OPEN_STATUSES and item.expires_at and item.expires_at < now:
        item.status = "expired"


def _target_supplier_scope(item: BuyRequest | dict) -> tuple[bool, int | None]:
    raw_requirements = item.requirements if isinstance(item, BuyRequest) else item
    requirements = raw_requirements if isinstance(raw_requirements, dict) else {}
    if "supplier_id" not in requirements or requirements.get("supplier_id") in (None, ""):
        return False, None
    raw_value = requirements.get("supplier_id")
    if isinstance(raw_value, bool):
        return True, None
    try:
        supplier_id = int(raw_value)
    except (TypeError, ValueError):
        return True, None
    return True, supplier_id if supplier_id > 0 else None


def _supplier_can_view(item: BuyRequest, user: User, supplier: Supplier, db: Session) -> bool:
    if item.user_id == user.id:
        return True
    has_own_history = db.query(BuyRequestQuote.id).filter(
        BuyRequestQuote.buy_request_id == item.id,
        BuyRequestQuote.supplier_id == supplier.id,
    ).first() is not None
    if has_own_history:
        return True
    has_own_deal = db.query(BuyRequestDeal.id).filter(
        BuyRequestDeal.buy_request_id == item.id,
        BuyRequestDeal.supplier_id == supplier.id,
    ).first() is not None
    if has_own_deal:
        return True
    if item.status not in OPEN_STATUSES:
        return False
    has_target, targeted_supplier_id = _target_supplier_scope(item)
    return not has_target or targeted_supplier_id == supplier.id


def _request_out(
    item: BuyRequest,
    db: Session,
    reveal_contact: bool = False,
    viewer_user_id: int | None = None,
    viewer_supplier_id: int | None = None,
    viewer_role: str = "buyer",
) -> dict:
    quote_count = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == item.id,
    ).count()
    show_buyer_identity = reveal_contact or viewer_role == "admin"
    buyer = db.query(User).filter(User.id == item.user_id).first()
    requirements = item.requirements or {}
    if not show_buyer_identity:
        requirements = _public_requirements(
            requirements,
            tuple(filter(None, (
                buyer.username if buyer else "",
                item.contact or "",
                item.phone or "",
                _mask_phone(item.phone) or "",
            ))),
        )
    _, targeted_supplier_id = _target_supplier_scope(item)
    target_supplier = (
        db.query(Supplier).filter(Supplier.id == targeted_supplier_id).first()
        if targeted_supplier_id is not None
        else None
    )
    return {
        "id": item.id,
        "user_id": item.user_id if show_buyer_identity else None,
        "buyer_name": buyer.username if show_buyer_identity and buyer else None,
        "request_type": item.request_type,
        "gpu_model": item.gpu_model,
        "gpu_variant": item.gpu_variant,
        "quantity": item.quantity,
        "gpu_hours": item.gpu_hours,
        "max_unit_price": float(item.max_unit_price) if item.max_unit_price is not None else None,
        "budget": float(item.budget) if item.budget is not None else None,
        "currency": item.currency,
        "region": item.region,
        "billing_mode": item.billing_mode,
        "requirements": requirements,
        "contact": item.contact if show_buyer_identity else None,
        "phone": item.phone if show_buyer_identity else None,
        "status": item.status,
        "quote_count": quote_count,
        "expires_at": item.expires_at.isoformat(timespec="seconds") + "Z" if item.expires_at else None,
        "created_at": item.created_at.isoformat(timespec="seconds") + "Z" if item.created_at else None,
        "updated_at": item.updated_at.isoformat(timespec="seconds") + "Z" if item.updated_at else None,
        "legacy": item.legacy_offline_purchase_id is not None,
        "is_own": viewer_user_id is not None and item.user_id == viewer_user_id,
        "targeted_supplier_id": targeted_supplier_id,
        "targeted_to_me": targeted_supplier_id is not None and targeted_supplier_id == viewer_supplier_id,
        "target_supplier": (
            {"id": target_supplier.id, "company_name": target_supplier.company_name}
            if target_supplier
            else None
        ),
    }


def _quote_out(
    item: BuyRequestQuote,
    db: Session,
    *,
    viewer_role: str = "buyer",
    viewer_supplier_id: int | None = None,
) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == item.supplier_id).first()
    revisions = db.query(BuyRequestQuoteRevision).filter(
        BuyRequestQuoteRevision.quote_id == item.id,
    ).order_by(
        BuyRequestQuoteRevision.revision_number.asc(),
        BuyRequestQuoteRevision.id.asc(),
    ).all()
    request = db.query(BuyRequest).filter(BuyRequest.id == item.buy_request_id).first()
    latest = revisions[-1] if revisions else None
    revision_payloads = [matchmaking.revision_out(row) for row in revisions]
    if viewer_role == "buyer":
        for payload in revision_payloads:
            payload["message"] = _public_quote_message(payload.get("message"), supplier)
    no_active_deal = db.query(BuyRequestDeal.id).filter(
        BuyRequestDeal.buy_request_id == item.buy_request_id,
        BuyRequestDeal.active_slot.isnot(None),
    ).first() is None
    can_counter = bool(
        request
        and request.status in OPEN_STATUSES
        and item.status == "active"
        and no_active_deal
        and latest
        and (
            (viewer_role == "buyer" and latest.proposer_role == "supplier")
            or (
                viewer_role == "supplier"
                and viewer_supplier_id == item.supplier_id
                and latest.proposer_role == "buyer"
            )
        )
    )
    result = {
        "id": item.id,
        "buy_request_id": item.buy_request_id,
        "supplier_id": item.supplier_id,
        "supplier_name": supplier.company_name if supplier else "",
        "supplier_rating": supplier.rating if supplier else None,
        "unit_price": float(item.unit_price) if item.unit_price is not None else None,
        "total_price": float(item.total_price),
        "currency": item.currency,
        "available_at": item.available_at.isoformat(timespec="seconds") + "Z" if item.available_at else None,
        "message": (
            _public_quote_message(item.message, supplier)
            if viewer_role == "buyer"
            else item.message
        ),
        "status": item.status,
        "expires_at": item.expires_at.isoformat(timespec="seconds") + "Z" if item.expires_at else None,
        "created_at": item.created_at.isoformat(timespec="seconds") + "Z" if item.created_at else None,
        "revision_count": len(revisions),
        "latest_revision": revision_payloads[-1] if revision_payloads else None,
        "revisions": revision_payloads,
        "can_counter": can_counter,
        "can_withdraw": bool(
            viewer_role == "supplier"
            and viewer_supplier_id == item.supplier_id
            and request
            and request.status in OPEN_STATUSES
            and item.status == "active"
            and no_active_deal
        ),
    }
    return result


def _approved_supplier(user: User, db: Session) -> Supplier:
    if user.supplier_status != "approved":
        raise BizError("需要完成商家认证")
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id, Supplier.status == "approved").first()
    if not supplier:
        raise BizError("商家资料不存在")
    return supplier


def _begin_serialized_matchmaking_transaction(db: Session) -> None:
    """Serialize matchmaking writes on SQLite; constraints cover other databases."""

    if db.get_bind().dialect.name != "sqlite":
        return
    # Authentication opens a read transaction before the endpoint. Restart it
    # as IMMEDIATE before any admission read so concurrent processes cannot both
    # observe the same idempotency key or supplier/request pair as available.
    try:
        if db.in_transaction():
            db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as exc:
        db.rollback()
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise BizError(_MATCHMAKING_WRITE_CONFLICT_MESSAGE, status_code=409) from exc
        raise


def _find_request_by_client_id(
    db: Session,
    user_id: int,
    client_request_id: str,
) -> BuyRequest | None:
    return db.query(BuyRequest).filter(
        BuyRequest.user_id == user_id,
        BuyRequest.client_request_id == client_request_id,
    ).first()


def _decimal_request_value_matches(
    stored: Decimal | None,
    submitted: float | None,
    quantum: Decimal,
) -> bool:
    if stored is None or submitted is None:
        return stored is None and submitted is None
    return Decimal(str(stored)).quantize(
        quantum,
        rounding=ROUND_HALF_UP,
    ) == Decimal(str(submitted)).quantize(
        quantum,
        rounding=ROUND_HALF_UP,
    )


def _quantized_request_decimal(value: float | None, quantum: Decimal) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def _same_create_request(
    item: BuyRequest,
    data: BuyRequestIn,
    *,
    gpu_model: str,
    requirements: dict,
    contact: str,
    phone: str | None,
) -> bool:
    if item.created_at is None or item.expires_at is None:
        expiry_hours_match = False
    else:
        expiry_hours_match = round(
            (item.expires_at - item.created_at).total_seconds() / 3600
        ) == data.expires_in_hours
    return (
        item.request_type == data.request_type
        and item.gpu_model == gpu_model
        and item.gpu_variant == data.gpu_variant
        and int(item.quantity) == data.quantity
        and item.gpu_hours == data.gpu_hours
        and _decimal_request_value_matches(
            item.max_unit_price,
            data.max_unit_price,
            Decimal("0.000001"),
        )
        and _decimal_request_value_matches(
            item.budget,
            data.budget,
            Decimal("0.01"),
        )
        and item.currency == data.currency.upper()
        and item.region == data.region
        and item.billing_mode == data.billing_mode
        and (item.requirements or {}) == requirements
        and (not data.contact or (item.contact or "") == contact)
        and (
            not data.phone
            or (_normalize_contact_phone(item.phone) or item.phone or "") == (phone or "")
        )
        and expiry_hours_match
    )


@admin_router.get("")
def admin_list_requests(
    status: str | None = Query(default=None, max_length=24),
    request_type: str | None = Query(default=None, max_length=16),
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = _now()
    expiring = db.query(BuyRequest).filter(
        BuyRequest.status.in_(OPEN_STATUSES),
        BuyRequest.expires_at.isnot(None),
        BuyRequest.expires_at < now,
    ).all()
    for row in expiring:
        row.status = "expired"
    if expiring:
        db.commit()
    query = db.query(BuyRequest)
    if status and status.strip():
        query = query.filter(BuyRequest.status == status.strip())
    if request_type and request_type.strip():
        query = query.filter(BuyRequest.request_type == request_type.strip())
    if keyword and keyword.strip():
        normalized = keyword.strip()
        query = query.join(User, User.id == BuyRequest.user_id).filter(or_(
            BuyRequest.gpu_model.contains(normalized),
            BuyRequest.gpu_variant.contains(normalized),
            BuyRequest.contact.contains(normalized),
            BuyRequest.phone.contains(normalized),
            User.username.contains(normalized),
        ))
    total = query.count()
    items = query.order_by(BuyRequest.created_at.desc(), BuyRequest.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    for item in items:
        _expire_if_needed(item, _now())
    db.commit()
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _request_out(
                item,
                db,
                reveal_contact=True,
                viewer_user_id=actor.id,
                viewer_role="admin",
            )
            for item in items
        ],
    })


@admin_router.get("/{request_id}")
def admin_request_detail(
    request_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    _expire_if_needed(item, _now())
    db.commit()
    quotes = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == item.id,
    ).order_by(BuyRequestQuote.created_at.desc()).all()
    deal = matchmaking.latest_visible_deal(
        db,
        item,
        viewer_role="admin",
        viewer_user_id=actor.id,
    )
    return success({
        "request": _request_out(
            item,
            db,
            reveal_contact=True,
            viewer_user_id=actor.id,
            viewer_role="admin",
        ),
        "quotes": [_quote_out(quote, db, viewer_role="admin") for quote in quotes],
        "deal": matchmaking.deal_out(db, deal, viewer_role="admin") if deal else None,
        "events": matchmaking.events_out(
            db,
            item,
            viewer_role="admin",
            deal=deal,
        ),
    })


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = _now()
    items = db.query(BuyRequest).filter(BuyRequest.user_id == user.id).all()
    for item in items:
        _expire_if_needed(item, now)
    db.commit()
    active_ids = [item.id for item in items if item.status in (
        "published", "quoting", "buyer_selected", "platform_review",
        "credential_pending", "credential_rejected", "credential_submitted",
        "credential_released", "delivery_disputed", "quote_selected",
        "pending_payment", "processing",
    )]
    new_quotes = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id.in_(active_ids or [-1]),
        BuyRequestQuote.status == "active",
    ).count()
    return success({
        "active": len(active_ids),
        "new_quotes": new_quotes,
        "pending_confirmation": sum(
            1 for item in items if item.status in (
                "buyer_selected", "platform_review", "credential_pending",
                "credential_rejected", "credential_submitted", "credential_released",
                "delivery_disputed", "quote_selected",
            )
        ),
    })


@router.get("")
def list_requests(
    request_type: str | None = None,
    view: str = "buyer",
    quoted_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _now()
    query = db.query(BuyRequest)
    if request_type in ("online", "offline"):
        query = query.filter(BuyRequest.request_type == request_type)
    supplier = None
    if view == "seller":
        supplier = _approved_supplier(user, db)
        if quoted_only:
            query = query.filter(
                db.query(BuyRequestQuote.id).filter(
                    BuyRequestQuote.buy_request_id == BuyRequest.id,
                    BuyRequestQuote.supplier_id == supplier.id,
                ).exists()
            )
    else:
        if quoted_only:
            raise BizError("我的报价筛选仅适用于商家视图", status_code=422)
        query = query.filter(BuyRequest.user_id == user.id)
    items = query.order_by(BuyRequest.created_at.desc()).all()
    for item in items:
        _expire_if_needed(item, now)
    if supplier:
        items = [item for item in items if _supplier_can_view(item, user, supplier, db)]
    items = items[:100]
    db.commit()
    return success([
        _request_out(
            item,
            db,
            reveal_contact=item.user_id == user.id,
            viewer_user_id=user.id,
            viewer_supplier_id=supplier.id if supplier else None,
            viewer_role=(
                "buyer" if item.user_id == user.id else "supplier"
            ),
        )
        for item in items
    ])


@router.post("")
def create_request(
    data: BuyRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    if data.request_type not in ("online", "offline"):
        raise BizError("求购类型不正确")
    model = canonicalize_gpu(data.gpu_model) or data.gpu_model.strip().upper().replace(" ", "")
    if not model:
        raise BizError("请输入 GPU 型号")
    if data.request_type == "online" and not data.gpu_hours:
        raise BizError("请输入总卡时")
    user_id = int(user.id)
    contact = (data.contact or user.username or "").strip()
    phone = _normalize_contact_phone(data.phone) or _normalize_contact_phone(user.phone)
    if data.request_type == "offline" and (not contact or not phone):
        raise BizError("线下求购需要联系人和联系电话")
    requirements = data.requirements or {}
    client_request_id = str(data.client_request_id or "").strip() or None
    if client_request_id:
        _begin_serialized_matchmaking_transaction(db)
        existing = _find_request_by_client_id(db, user_id, client_request_id)
        if existing:
            if not _same_create_request(
                existing,
                data,
                gpu_model=model,
                requirements=requirements,
                contact=contact,
                phone=phone,
            ):
                db.rollback()
                raise BizError("重复请求参数不一致，请重新提交", status_code=409)
            db.commit()
            return success(_request_out(
                existing,
                db,
                reveal_contact=True,
                viewer_user_id=user_id,
            ))
    has_target, targeted_supplier_id = _target_supplier_scope(requirements)
    if has_target:
        target_supplier = (
            db.query(Supplier).filter(
                Supplier.id == targeted_supplier_id,
                Supplier.status == "approved",
            ).first()
            if targeted_supplier_id is not None
            else None
        )
        if not target_supplier:
            raise BizError("指定商家不存在或尚未通过认证")
    item = BuyRequest(
        user_id=user_id,
        client_request_id=client_request_id,
        request_type=data.request_type,
        gpu_model=model,
        gpu_variant=data.gpu_variant,
        quantity=data.quantity,
        gpu_hours=data.gpu_hours,
        max_unit_price=_quantized_request_decimal(
            data.max_unit_price,
            Decimal("0.000001"),
        ),
        budget=_quantized_request_decimal(data.budget, Decimal("0.01")),
        currency=data.currency.upper(),
        region=data.region,
        billing_mode=data.billing_mode,
        requirements=requirements,
        contact=contact,
        phone=phone,
        status="published",
        expires_at=_now() + timedelta(hours=data.expires_in_hours),
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            _find_request_by_client_id(db, user_id, client_request_id)
            if client_request_id
            else None
        )
        if existing:
            if not _same_create_request(
                existing,
                data,
                gpu_model=model,
                requirements=requirements,
                contact=contact,
                phone=phone,
            ):
                db.rollback()
                raise BizError("重复请求参数不一致，请重新提交", status_code=409) from None
            db.commit()
            return success(_request_out(
                existing,
                db,
                reveal_contact=True,
                viewer_user_id=user_id,
            ))
        raise BizError("提交需求冲突，请重试", status_code=409) from None
    db.refresh(item)
    return success(_request_out(item, db, reveal_contact=True, viewer_user_id=user_id))


@router.get("/{request_id}")
def request_detail(
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    _expire_if_needed(item, _now())
    owner = item.user_id == user.id
    supplier = None
    if not owner:
        supplier = _approved_supplier(user, db)
        if not _supplier_can_view(item, user, supplier, db):
            db.commit()
            raise BizError("求购不存在", status_code=404)
    elif user.supplier_status == "approved":
        supplier = db.query(Supplier).filter(
            Supplier.user_id == user.id,
            Supplier.status == "approved",
        ).first()
    db.commit()
    quotes_query = db.query(BuyRequestQuote).filter(BuyRequestQuote.buy_request_id == item.id)
    if not owner and supplier:
        quotes_query = quotes_query.filter(BuyRequestQuote.supplier_id == supplier.id)
    quotes = quotes_query.order_by(BuyRequestQuote.created_at.desc()).all()
    viewer_role = "buyer" if owner else "supplier"
    deal = matchmaking.latest_visible_deal(
        db,
        item,
        viewer_role=viewer_role,
        viewer_user_id=user.id,
        viewer_supplier_id=supplier.id if supplier else None,
    )
    return success({
        "request": _request_out(
            item,
            db,
            reveal_contact=owner,
            viewer_user_id=user.id,
            viewer_supplier_id=supplier.id if supplier else None,
            viewer_role=viewer_role,
        ),
        "quotes": [
            _quote_out(
                quote,
                db,
                viewer_role=viewer_role,
                viewer_supplier_id=supplier.id if supplier else None,
            )
            for quote in quotes
        ],
        "deal": matchmaking.deal_out(db, deal, viewer_role=viewer_role) if deal else None,
        "events": matchmaking.events_out(
            db,
            item,
            viewer_role=viewer_role,
            viewer_supplier_id=supplier.id if supplier else None,
            deal=deal,
        ),
    })


@router.post("/{request_id}/quotes")
def create_quote(
    request_id: int,
    data: QuoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(
        BuyRequest.id == request_id,
    ).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    _expire_if_needed(item, _now())
    if not _supplier_can_view(item, user, supplier, db):
        db.commit()
        raise BizError("求购不存在", status_code=404)
    if item.user_id == user.id:
        raise BizError("不能给自己的求购报价")
    if item.status not in OPEN_STATUSES:
        raise BizError("该求购当前不能报价")
    existing = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == item.id,
        BuyRequestQuote.supplier_id == supplier.id,
        BuyRequestQuote.status == "active",
    ).first()
    if existing and existing.expires_at and existing.expires_at < _now():
        existing.status = "expired"
        latest = matchmaking.latest_revision(db, existing.id)
        if latest and latest.status == "active":
            latest.status = "expired"
        existing = None
    if existing:
        raise BizError("已经提交过有效报价")
    quote = BuyRequestQuote(
        buy_request_id=item.id,
        supplier_id=supplier.id,
        unit_price=Decimal(str(data.unit_price)) if data.unit_price is not None else None,
        total_price=Decimal(str(data.total_price)),
        currency=data.currency.upper(),
        available_at=(
            data.available_at.astimezone(timezone.utc).replace(tzinfo=None)
            if data.available_at and data.available_at.tzinfo
            else data.available_at
        ),
        message=data.message,
        status="active",
        expires_at=_now() + timedelta(hours=data.expires_in_hours),
    )
    item.status = "quoting"
    db.add(quote)
    db.flush()
    matchmaking.create_initial_revision(db, item, quote, user)
    db.commit()
    db.refresh(quote)
    return success(_quote_out(
        quote,
        db,
        viewer_role="supplier",
        viewer_supplier_id=supplier.id,
    ))


@router.post("/{request_id}/quotes/{quote_id}/counter")
def counter_quote(
    request_id: int,
    quote_id: int,
    data: QuoteRevisionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    quote = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.buy_request_id == request_id,
    ).with_for_update().first()
    if not item or not quote:
        raise BizError("报价不存在", status_code=404)
    _expire_if_needed(item, _now())
    quote_supplier = db.query(Supplier).filter(
        Supplier.id == quote.supplier_id,
        Supplier.status == "approved",
    ).first()
    if not quote_supplier:
        raise BizError("报价不存在", status_code=404)
    if user.id != item.user_id:
        actor_supplier = _approved_supplier(user, db)
        if actor_supplier.id != quote_supplier.id:
            raise BizError("报价不存在", status_code=404)
        viewer_role = "supplier"
        viewer_supplier_id = actor_supplier.id
    else:
        viewer_role = "buyer"
        viewer_supplier_id = None
    matchmaking.revise_quote(db, item, quote, user, quote_supplier, data)
    db.commit()
    db.refresh(quote)
    return success(_quote_out(
        quote,
        db,
        viewer_role=viewer_role,
        viewer_supplier_id=viewer_supplier_id,
    ))


@router.post("/{request_id}/quotes/{quote_id}/withdraw")
def withdraw_quote(
    request_id: int,
    quote_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    quote = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.buy_request_id == request_id,
    ).with_for_update().first()
    if not item or not quote:
        raise BizError("报价不存在", status_code=404)
    matchmaking.withdraw_quote(db, item, quote, user, supplier)
    db.commit()
    return success({
        "request_id": item.id,
        "quote_id": quote.id,
        "status": quote.status,
        "request_status": item.status,
    })


@router.post("/{request_id}/quotes/{quote_id}/select")
def select_quote(
    request_id: int,
    quote_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # In matchmaking mode this records only a cooperation intention for
    # platform coordination. It must never create an Order, freeze a Wallet or
    # append a Ledger entry. Direct-trade deployments retain the historical
    # quote-selected semantics for compatibility.
    if not direct_trade_enabled():
        require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(
        BuyRequest.id == request_id,
        BuyRequest.user_id == user.id,
    ).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    _expire_if_needed(item, _now())
    quote = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.buy_request_id == item.id,
    ).with_for_update().first()
    if not quote:
        raise BizError("报价不存在或已失效", status_code=404)
    if direct_trade_enabled():
        if item.status not in OPEN_STATUSES:
            raise BizError("该求购当前不能确认合作意向", status_code=409)
        if quote.status != "active":
            raise BizError("报价不存在或已失效")
        if quote.expires_at and quote.expires_at < _now():
            quote.status = "expired"
            db.commit()
            raise BizError("报价已过期")
        db.query(BuyRequestQuote).filter(
            BuyRequestQuote.buy_request_id == item.id,
            BuyRequestQuote.id != quote.id,
            BuyRequestQuote.status == "active",
        ).update({"status": "declined"}, synchronize_session=False)
        quote.status = "selected"
        item.status = "quote_selected"
        db.commit()
        return success({
            "request_id": item.id,
            "quote_id": quote.id,
            "status": item.status,
            "quote_status": quote.status,
            "commerce_mode": commerce_mode(),
        })
    else:
        deal = matchmaking.select_quote(db, item, quote, user)
    db.commit()
    return success({
        "request_id": item.id,
        "quote_id": quote.id,
        "status": item.status,
        "quote_status": quote.status,
        "commerce_mode": commerce_mode(),
        "deal": matchmaking.deal_out(db, deal, viewer_role="buyer"),
    })


@router.post("/{request_id}/deals/{deal_id}/supplier-confirm")
def supplier_confirm_deal(
    request_id: int,
    deal_id: int,
    data: DealActionIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.supplier_decision(
        db,
        item,
        deal,
        user,
        supplier,
        confirm=True,
        expected_version=data.expected_version if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="supplier"))


@router.post("/{request_id}/deals/{deal_id}/supplier-decline")
def supplier_decline_deal(
    request_id: int,
    deal_id: int,
    data: DealReasonIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.supplier_decision(
        db,
        item,
        deal,
        user,
        supplier,
        confirm=False,
        expected_version=data.expected_version if data else None,
        reason=data.reason if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="supplier"))


@router.post("/{request_id}/deals/{deal_id}/credential")
def supplier_submit_credential(
    request_id: int,
    deal_id: int,
    data: MatchmakingCredentialIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    credential = matchmaking.submit_credential(db, item, deal, user, supplier, data)
    db.commit()
    result = matchmaking.deal_out(db, deal, viewer_role="supplier")
    result["credential_status"] = credential.status
    return success(result)


@router.get("/{request_id}/deals/{deal_id}/credential")
def buyer_get_credential(
    request_id: int,
    deal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    deal = matchmaking.get_deal(db, request_id, deal_id)
    return success(matchmaking.buyer_read_credential(db, deal, user))


@router.post("/{request_id}/deals/{deal_id}/confirm-delivery")
def buyer_confirm_delivery(
    request_id: int,
    deal_id: int,
    data: DealActionIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.buyer_delivery_decision(
        db,
        item,
        deal,
        user,
        confirm=True,
        expected_version=data.expected_version if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="buyer"))


@router.post("/{request_id}/deals/{deal_id}/report-delivery")
def buyer_report_delivery(
    request_id: int,
    deal_id: int,
    data: DeliveryIssueIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.buyer_delivery_decision(
        db,
        item,
        deal,
        user,
        confirm=False,
        expected_version=data.expected_version,
        reason=data.reason,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="buyer"))


@admin_router.post("/{request_id}/deals/{deal_id}/approve")
def admin_approve_deal(
    request_id: int,
    deal_id: int,
    data: DealActionIn | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.admin_review(
        db,
        item,
        deal,
        actor,
        approve=True,
        expected_version=data.expected_version if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="admin"))


@admin_router.post("/{request_id}/deals/{deal_id}/reject")
def admin_reject_deal(
    request_id: int,
    deal_id: int,
    data: DealReasonIn | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.admin_review(
        db,
        item,
        deal,
        actor,
        approve=False,
        expected_version=data.expected_version if data else None,
        reason=data.reason if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="admin"))


@admin_router.get("/{request_id}/deals/{deal_id}/credential")
def admin_get_credential(
    request_id: int,
    deal_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    deal = matchmaking.get_deal(db, request_id, deal_id)
    result = matchmaking.inspect_credential(db, deal, actor)
    db.commit()
    return success(result)


@admin_router.post("/{request_id}/deals/{deal_id}/credential/release")
def admin_release_credential(
    request_id: int,
    deal_id: int,
    data: DealActionIn | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.admin_credential_decision(
        db,
        item,
        deal,
        actor,
        release_to_buyer=True,
        expected_version=data.expected_version if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="admin"))


@admin_router.post("/{request_id}/deals/{deal_id}/credential/reject")
def admin_reject_credential(
    request_id: int,
    deal_id: int,
    data: DealReasonIn | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    require_matchmaking_enabled()
    _begin_serialized_matchmaking_transaction(db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).with_for_update().first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    deal = matchmaking.get_deal(db, request_id, deal_id)
    matchmaking.admin_credential_decision(
        db,
        item,
        deal,
        actor,
        release_to_buyer=False,
        expected_version=data.expected_version if data else None,
        reason=data.reason if data else None,
    )
    db.commit()
    return success(matchmaking.deal_out(db, deal, viewer_role="admin"))
