"""Administrator read APIs with auditable client-origin filtering.

``created_platform`` is an observability dimension copied from the server-side
authenticated session.  It is deliberately never used as an authorization
boundary: administrator access remains protected by ``require_admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Query as SqlAlchemyQuery, Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.bank_card import BankCard
from app.models.external_identity import ExternalIdentity
from app.models.order import Order
from app.models.payment import PaymentOrder
from app.models.product import Product
from app.models.user import User
from app.models.verification import Verification
from app.models.withdrawal import WithdrawalOrder
from app.services.auth_session import AUDIT_PLATFORMS, AuditPlatform
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/admin", tags=["admin"])

def _page(page: int, page_size: int) -> None:
    if page < 1 or page_size < 1 or page_size > 100:
        raise BizError("分页参数无效")


def _filter_platform(
    query: SqlAlchemyQuery,
    model: type,
    platform: AuditPlatform | None,
) -> SqlAlchemyQuery:
    return query.filter(model.created_platform == platform) if platform else query


def _masked_phone(user: User) -> str | None:
    value = str(user.phone or "")
    if len(value) < 7:
        return None
    return f"{value[:3]}****{value[-4:]}"


@router.get("/overview")
def overview(
    platform: AuditPlatform | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    models = {
        "users": User,
        "orders": Order,
        "recharge_orders": PaymentOrder,
        "verifications": Verification,
        "bank_cards": BankCard,
        "withdrawals": WithdrawalOrder,
    }

    def counts_for(source: str | None) -> dict[str, int]:
        return {
            name: _filter_platform(db.query(model), model, source).count()
            for name, model in models.items()
        }

    sources = (platform,) if platform else AUDIT_PLATFORMS
    return success({
        "created_platform": platform,
        "counts": counts_for(platform),
        "by_platform": [
            {"created_platform": source, "counts": counts_for(source)}
            for source in sources
        ],
    })


@router.get("/users")
def users(
    platform: AuditPlatform | None = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(User), User, platform)
    if keyword:
        normalized = keyword.strip()
        if normalized:
            query = query.filter(
                (User.username.contains(normalized)) | (User.phone.contains(normalized))
            )
    total = query.count()
    rows = query.order_by(User.created_at.desc(), User.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    bound_user_ids = {
        row[0]
        for row in db.query(ExternalIdentity.user_id).filter(
            ExternalIdentity.provider == "kai",
            ExternalIdentity.user_id.in_([item.id for item in rows] or [-1]),
        ).all()
    }
    items = [{
        "id": row.id,
        "username": row.username,
        "phone_masked": _masked_phone(row),
        "phone_bound": bool(row.phone_bound),
        "role": row.role,
        "supplier_status": row.supplier_status,
        "kai_identity_bound": row.id in bound_user_ids,
        "created_platform": row.created_platform or "legacy",
        "created_at": row.created_at,
    } for row in rows]
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/orders")
def orders(
    platform: AuditPlatform | None = None,
    status: str | None = Query(default=None, max_length=24),
    order_no: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(Order), Order, platform)
    if status:
        query = query.filter(Order.status == status)
    if order_no:
        query = query.filter(Order.order_no.contains(order_no.strip()))
    total = query.count()
    rows = query.order_by(Order.created_at.desc(), Order.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    items = []
    for row in rows:
        owner = db.query(User).filter(User.id == row.user_id).first()
        product = db.query(Product).filter(Product.id == row.product_id).first()
        items.append({
            "id": row.id,
            "order_no": row.order_no,
            "user": {"id": row.user_id, "username": owner.username if owner else None},
            "product": {
                "id": row.product_id,
                "name": product.name if product else None,
                "gpu_model": product.gpu_model if product else None,
            },
            "quantity": row.quantity,
            "purchase_hours": row.purchase_hours,
            "cycle_days": row.cycle_days,
            "purchase_type": row.purchase_type,
            "amount_card_hours": float(row.amount),
            "status": row.status,
            "created_platform": row.created_platform or "legacy",
            "last_modified_platform": row.last_modified_platform or "legacy",
            "start_at": row.start_at,
            "end_at": row.end_at,
            "created_at": row.created_at,
        })
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/recharge-orders")
@router.get("/payment-orders", include_in_schema=False)
def recharge_orders(
    platform: AuditPlatform | None = None,
    status: str | None = Query(default=None, max_length=24),
    order_no: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(PaymentOrder), PaymentOrder, platform)
    if status:
        query = query.filter(PaymentOrder.status == status)
    if order_no:
        query = query.filter(PaymentOrder.order_no.contains(order_no.strip()))
    total = query.count()
    rows = query.order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    items = []
    for row in rows:
        owner = db.query(User).filter(User.id == row.user_id).first()
        items.append({
            "id": row.id,
            "order_no": row.order_no,
            "user": {"id": row.user_id, "username": owner.username if owner else None},
            "provider": row.provider,
            "provider_trade_no": row.provider_trade_no,
            "channel": row.channel,
            "status": row.status,
            "amount_cny": float(row.amount_cny),
            "card_hours": float(row.card_hours),
            "card_hour_rate": float(row.card_hour_rate),
            "created_platform": row.created_platform or "legacy",
            "last_modified_platform": row.last_modified_platform or "legacy",
            "expires_at": row.expires_at,
            "paid_at": row.paid_at,
            "credited_at": row.credited_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        })
    return success({"total": total, "page": page, "page_size": page_size, "items": items})
