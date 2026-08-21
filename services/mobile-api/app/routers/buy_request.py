from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.buy_request import BuyRequest, BuyRequestQuote
from app.models.supplier import Supplier
from app.models.user import User
from app.services.gpu_catalog import canonicalize_gpu
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/buy-requests", tags=["buy-request"])
OPEN_STATUSES = ("published", "quoting")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BuyRequestIn(BaseModel):
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
    phone: str | None = None
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


class QuoteIn(BaseModel):
    unit_price: float | None = Field(default=None, ge=0)
    total_price: float = Field(ge=0)
    currency: str = "CNY"
    available_at: datetime | None = None
    message: str | None = Field(default=None, max_length=1000)
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


def _mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def _expire_if_needed(item: BuyRequest, now: datetime) -> None:
    if item.status in OPEN_STATUSES and item.expires_at and item.expires_at < now:
        item.status = "expired"


def _request_out(item: BuyRequest, db: Session, reveal_contact: bool = False) -> dict:
    quote_count = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == item.id,
        BuyRequestQuote.status.in_(("active", "selected")),
    ).count()
    buyer = db.query(User).filter(User.id == item.user_id).first()
    return {
        "id": item.id,
        "user_id": item.user_id,
        "buyer_name": buyer.username if buyer else "",
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
        "requirements": item.requirements or {},
        "contact": item.contact if reveal_contact else None,
        "phone": item.phone if reveal_contact else _mask_phone(item.phone),
        "status": item.status,
        "quote_count": quote_count,
        "expires_at": item.expires_at.isoformat(timespec="seconds") + "Z" if item.expires_at else None,
        "created_at": item.created_at.isoformat(timespec="seconds") + "Z" if item.created_at else None,
        "updated_at": item.updated_at.isoformat(timespec="seconds") + "Z" if item.updated_at else None,
        "legacy": item.legacy_offline_purchase_id is not None,
    }


def _quote_out(item: BuyRequestQuote, db: Session) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == item.supplier_id).first()
    return {
        "id": item.id,
        "buy_request_id": item.buy_request_id,
        "supplier_id": item.supplier_id,
        "supplier_name": supplier.company_name if supplier else "",
        "supplier_rating": supplier.rating if supplier else None,
        "unit_price": float(item.unit_price) if item.unit_price is not None else None,
        "total_price": float(item.total_price),
        "currency": item.currency,
        "available_at": item.available_at.isoformat(timespec="seconds") + "Z" if item.available_at else None,
        "message": item.message,
        "status": item.status,
        "expires_at": item.expires_at.isoformat(timespec="seconds") + "Z" if item.expires_at else None,
        "created_at": item.created_at.isoformat(timespec="seconds") + "Z" if item.created_at else None,
    }


def _approved_supplier(user: User, db: Session) -> Supplier:
    if user.supplier_status != "approved":
        raise BizError("需要完成商家认证")
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id, Supplier.status == "approved").first()
    if not supplier:
        raise BizError("商家资料不存在")
    return supplier


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = _now()
    items = db.query(BuyRequest).filter(BuyRequest.user_id == user.id).all()
    for item in items:
        _expire_if_needed(item, now)
    db.commit()
    active_ids = [item.id for item in items if item.status in ("published", "quoting", "quote_selected", "pending_payment", "processing")]
    new_quotes = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id.in_(active_ids or [-1]),
        BuyRequestQuote.status == "active",
    ).count()
    return success({
        "active": len(active_ids),
        "new_quotes": new_quotes,
        "pending_confirmation": sum(1 for item in items if item.status == "quote_selected"),
    })


@router.get("")
def list_requests(
    request_type: str | None = None,
    view: str = "buyer",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _now()
    query = db.query(BuyRequest)
    if request_type in ("online", "offline"):
        query = query.filter(BuyRequest.request_type == request_type)
    if view == "seller":
        _approved_supplier(user, db)
        query = query.filter(BuyRequest.user_id != user.id, BuyRequest.status.in_(OPEN_STATUSES))
    else:
        query = query.filter(BuyRequest.user_id == user.id)
    items = query.order_by(BuyRequest.created_at.desc()).limit(100).all()
    for item in items:
        _expire_if_needed(item, now)
    db.commit()
    return success([_request_out(item, db, reveal_contact=item.user_id == user.id) for item in items])


@router.post("")
def create_request(
    data: BuyRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.request_type not in ("online", "offline"):
        raise BizError("求购类型不正确")
    model = canonicalize_gpu(data.gpu_model) or data.gpu_model.strip().upper().replace(" ", "")
    if not model:
        raise BizError("请输入 GPU 型号")
    if data.request_type == "online" and not data.gpu_hours:
        raise BizError("请输入总卡时")
    contact = (data.contact or user.username or "").strip()
    phone = (data.phone or user.phone or "").strip()
    if data.request_type == "offline" and (not contact or not phone):
        raise BizError("线下求购需要联系人和联系电话")
    item = BuyRequest(
        user_id=user.id,
        request_type=data.request_type,
        gpu_model=model,
        gpu_variant=data.gpu_variant,
        quantity=data.quantity,
        gpu_hours=data.gpu_hours,
        max_unit_price=Decimal(str(data.max_unit_price)) if data.max_unit_price is not None else None,
        budget=Decimal(str(data.budget)) if data.budget is not None else None,
        currency=data.currency.upper(),
        region=data.region,
        billing_mode=data.billing_mode,
        requirements=data.requirements or {},
        contact=contact,
        phone=phone,
        status="published",
        expires_at=_now() + timedelta(hours=data.expires_in_hours),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return success(_request_out(item, db, reveal_contact=True))


@router.get("/{request_id}")
def request_detail(
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    owner = item.user_id == user.id
    supplier = None
    if not owner:
        supplier = _approved_supplier(user, db)
    quotes_query = db.query(BuyRequestQuote).filter(BuyRequestQuote.buy_request_id == item.id)
    if not owner and supplier:
        quotes_query = quotes_query.filter(BuyRequestQuote.supplier_id == supplier.id)
    quotes = quotes_query.order_by(BuyRequestQuote.created_at.desc()).all()
    return success({
        "request": _request_out(item, db, reveal_contact=owner),
        "quotes": [_quote_out(quote, db) for quote in quotes],
    })


@router.post("/{request_id}/quotes")
def create_quote(
    request_id: int,
    data: QuoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    supplier = _approved_supplier(user, db)
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id).first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    _expire_if_needed(item, _now())
    if item.user_id == user.id:
        raise BizError("不能给自己的求购报价")
    if item.status not in OPEN_STATUSES:
        raise BizError("该求购当前不能报价")
    existing = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == item.id,
        BuyRequestQuote.supplier_id == supplier.id,
        BuyRequestQuote.status == "active",
    ).first()
    if existing:
        raise BizError("已经提交过有效报价")
    quote = BuyRequestQuote(
        buy_request_id=item.id,
        supplier_id=supplier.id,
        unit_price=Decimal(str(data.unit_price)) if data.unit_price is not None else None,
        total_price=Decimal(str(data.total_price)),
        currency=data.currency.upper(),
        available_at=data.available_at.replace(tzinfo=None) if data.available_at and data.available_at.tzinfo else data.available_at,
        message=data.message,
        status="active",
        expires_at=_now() + timedelta(hours=data.expires_in_hours),
    )
    item.status = "quoting"
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return success(_quote_out(quote, db))


@router.post("/{request_id}/quotes/{quote_id}/select")
def select_quote(
    request_id: int,
    quote_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(BuyRequest).filter(BuyRequest.id == request_id, BuyRequest.user_id == user.id).first()
    if not item:
        raise BizError("求购不存在", status_code=404)
    quote = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.id == quote_id,
        BuyRequestQuote.buy_request_id == item.id,
        BuyRequestQuote.status == "active",
    ).first()
    if not quote:
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
    return success({"request_id": item.id, "quote_id": quote.id, "status": item.status})
