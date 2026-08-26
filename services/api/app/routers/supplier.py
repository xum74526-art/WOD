from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.core.sensitive import sensitive_capability_enabled
from app.db.session import get_db
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.merchant_settlement import MerchantSettlement
from app.models.order import Order
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from app.models.verification import Verification
from app.models.wallet import Wallet
from app.schemas.supplier import (
    SupplierDeviceCreateIn,
    SupplierDeviceUpdateIn,
    SupplierOut,
    SupplierProfileUpdateIn,
    SupplierRegisterIn,
)
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/supplier", tags=["supplier"])


class SupplierReviewIn(BaseModel):
    version: int = Field(default=1, ge=1)
    note: str | None = Field(default=None, max_length=1000)


def _identity_verified(user_id: int, db: Session) -> bool:
    return db.query(Verification.id).filter(
        Verification.user_id == user_id,
        Verification.status == "verified",
    ).first() is not None


def _admin_application_out(
    supplier: Supplier,
    applicant: User,
    *,
    identity_verified: bool,
) -> dict:
    return {
        "id": supplier.id,
        "company_name": supplier.company_name,
        "contact_name": supplier.contact,
        "contact_phone": supplier.phone,
        "region": supplier.region,
        "description": supplier.desc,
        "status": supplier.status,
        "identity_verified": identity_verified,
        # The mobile database predates review-event columns. Keep the Web
        # contract explicit without inventing reviewer or audit data.
        "review_note": None,
        "reviewed_at": None,
        "created_at": supplier.created_at,
        "updated_at": supplier.created_at,
        "version": 1,
        "reviewed_by": None,
        "applicant": {
            "id": applicant.id,
            "display_name": applicant.username,
            "email": None,
            "role": applicant.role,
            "status": applicant.supplier_status,
            "created_at": applicant.created_at,
        },
    }


def _public_supplier_out(supplier: Supplier) -> dict:
    """Compatibility-shaped store data without exposing a full phone number."""
    out = SupplierOut.model_validate(supplier).model_dump()
    phone = str(supplier.phone or "")
    out["phone"] = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else ""
    return out


def _get_supplier(user: User, db: Session) -> Supplier:
    s = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not s:
        raise BizError("您还不是供应商", status_code=403)
    if s.status == "pending":
        raise BizError("商家入驻申请审核中", status_code=403)
    if s.status != "approved":
        raise BizError("商家入驻申请未通过", status_code=403)
    return s


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    product_ids = [pid for (pid,) in db.query(Product.id).filter(Product.supplier_id == s.id, Product.status == "on").all()]
    query_product_ids = product_ids or [0]
    from datetime import datetime, timedelta, timezone
    today_start = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    # Only durable settlement facts are earnings. Historical completed orders
    # are intentionally not converted into withdrawable money on page load.
    today_revenue = float(db.query(func.coalesce(func.sum(MerchantSettlement.net_amount), 0)).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
        MerchantSettlement.settled_at >= today_start,
    ).scalar())
    total_revenue = float(db.query(func.coalesce(func.sum(MerchantSettlement.net_amount), 0)).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
    ).scalar())
    # 在售设备
    product_count = len(product_ids)
    total_stock = int(db.query(func.coalesce(func.sum(Product.stock), 0)).filter(
        Product.supplier_id == s.id, Product.status == "on"
    ).scalar() or 0)
    # 待交付
    pending_orders = db.query(Order).filter(
        Order.product_id.in_(query_product_ids), Order.status.in_(["paid", "delivering", "disputed"])
    ).count()
    # 完成订单数
    completed_orders = db.query(MerchantSettlement).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.source_type == "order",
        MerchantSettlement.status == "settled",
    ).count()
    # 设备概览
    products = db.query(Product).filter(Product.supplier_id == s.id, Product.status == "on").limit(5).all()
    device_list = []
    for p in products:
        stock_val = int(p.stock) if p.stock is not None else 0
        device_list.append({
            "id": p.id, "name": p.name, "gpu_model": p.gpu_model,
            "stock": stock_val, "price": float(p.price),
            "region": p.region_name or "-", "status": "online" if stock_val > 0 else "offline",
        })
    # 7天收益趋势（按日聚合）
    from collections import defaultdict
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_ago = now - timedelta(days=7)
    settlements = db.query(MerchantSettlement).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
        MerchantSettlement.settled_at >= week_ago,
    ).all()
    daily = defaultdict(float)
    for settlement in settlements:
        day = settlement.settled_at.strftime("%m-%d") if settlement.settled_at else "未知"
        daily[day] += float(settlement.net_amount)
    trend = [{"date": d, "amount": round(daily[d], 2)} for d in sorted(daily.keys())]
    return success({
        "company_name": s.company_name,
        "today_revenue": round(today_revenue, 2),
        "total_revenue": round(total_revenue, 2),
        "product_count": product_count,
        "total_stock": total_stock,
        "pending_orders": pending_orders,
        "completed_orders": completed_orders,
        "devices": device_list,
        "rating": s.rating,
        "order_count": s.order_count,
        "trend": trend,
    })


@router.get("/devices")
def device_list(status_filter: str = "on", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    q = db.query(Product).filter(Product.supplier_id == s.id)
    if status_filter == "on":
        q = q.filter(Product.status == "on")
    elif status_filter == "off":
        q = q.filter(Product.status == "off")
    products = q.order_by(Product.created_at.desc()).all()
    items = []
    for p in products:
        stock_val = int(p.stock) if p.stock is not None else 0
        order_count = db.query(Order).filter(Order.product_id == p.id).count()
        items.append({
            "id": p.id, "name": p.name, "gpu_model": p.gpu_model,
            "memory": p.memory, "price": float(p.price), "stock": stock_val,
            "region": p.region_name or "-", "city": p.city or "-",
            "order_count": order_count,
            "status": "online" if stock_val > 0 else "offline",
            "list_status": p.status,
            "image_url": p.image_url,
        })
    return success(items)


@router.post("/devices")
def add_device(data: SupplierDeviceCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    from decimal import Decimal
    p = Product(
        name=data.name, gpu_model=data.gpu_model,
        memory=data.memory, cuda=data.cuda,
        price=Decimal(str(data.price)), cycle=[],
        desc=data.desc, image_url=data.image_url,
        region_code=data.region_code,
        region_name=data.region_name,
        country_code="CN", city=data.city,
        stock=data.stock, reliability=98.0,
        supplier_id=s.id, status="on",
        market_source="wod",
        stock_semantics="supplier_reported_inventory",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return success({"id": p.id, "name": p.name, "status": "on"})


@router.put("/devices/{did}")
def update_device(did: int, data: SupplierDeviceUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    p = db.query(Product).filter(Product.id == did, Product.supplier_id == s.id).first()
    if not p:
        raise BizError("设备不存在", status_code=404)
    if data.price is not None:
        from decimal import Decimal
        p.price = Decimal(str(data.price))
    if data.stock is not None:
        p.stock = data.stock
    if data.name is not None:
        p.name = data.name
    if data.status is not None:
        p.status = data.status
    db.commit()
    return success({"id": did, "updated": True})


@router.delete("/devices/{did}")
def delete_device(did: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    p = db.query(Product).filter(Product.id == did, Product.supplier_id == s.id).first()
    if not p:
        raise BizError("设备不存在", status_code=404)
    p.status = "off"
    db.commit()
    return success({"id": did, "deleted": True})


@router.get("/revenue/detail")
def revenue_detail(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """收益明细：每笔已完成订单的收入"""
    s = _get_supplier(user, db)
    product_ids = [pid for (pid,) in db.query(Product.id).filter(Product.supplier_id == s.id).all()]
    if not product_ids:
        product_ids = [0]
    orders = db.query(Order).filter(
        Order.product_id.in_(product_ids),
        Order.status.in_(["completed", "running", "done", "paid", "delivering", "disputed"]),
    ).order_by(Order.created_at.desc()).limit(50).all()
    settlement_by_order = {
        settlement.order_id: settlement
        for settlement in db.query(MerchantSettlement).filter(
            MerchantSettlement.supplier_id == s.id,
            MerchantSettlement.source_type == "order",
            MerchantSettlement.order_id.in_([order.id for order in orders] or [0]),
        ).all()
    }
    items = []
    for o in orders:
        p = db.query(Product).filter(Product.id == o.product_id).first()
        buyer = db.query(User).filter(User.id == o.user_id).first()
        settlement = settlement_by_order.get(o.id)
        service_fee = float(settlement.service_fee_amount) if settlement else 0
        net_income = float(settlement.net_amount) if settlement else 0
        items.append({
            "order_no": o.order_no, "product_name": p.name if p else "-",
            "buyer_name": buyer.username if buyer else "匿名",
            "amount": float(o.amount), "service_fee": service_fee,
            "net_income": net_income,
            "settlement_status": settlement.status if settlement else (
                "pending" if o.status in {"paid", "delivering", "disputed"} else "historical_unreconciled"
            ),
            "status": o.status, "purchase_type": o.purchase_type,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return success(items)


@router.get("/wallet")
def supplier_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """商家钱包：收入统计"""
    s = _get_supplier(user, db)
    product_ids = [pid for (pid,) in db.query(Product.id).filter(Product.supplier_id == s.id).all()]
    if not product_ids:
        product_ids = [0]
    total_revenue = float(db.query(func.coalesce(func.sum(MerchantSettlement.net_amount), 0)).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
    ).scalar())
    # 待结算（paid+delivering的冻结资金）
    pending = db.query(Order).filter(
        Order.product_id.in_(product_ids),
        Order.status.in_(["paid", "delivering", "disputed"]),
    ).all()
    pending_amount = sum(float(o.amount) for o in pending)
    # 已完成的人工打款（冻结结算事件，不是二次钱包扣款）
    withdrawn = float(db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
        Ledger.user_id == user.id,
        Ledger.type == "withdraw_success",
        Ledger.direction == "internal",
    ).scalar())
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    # Only the durable wallet bucket is actionable. Calculated historical order
    # revenue must never become withdrawable merely because this page is opened.
    available = float(wallet.withdrawable_balance or 0) if wallet else 0
    # 今日收入
    from datetime import datetime, timedelta, timezone
    today_start = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    today_revenue = float(db.query(func.coalesce(func.sum(MerchantSettlement.net_amount), 0)).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
        MerchantSettlement.settled_at >= today_start,
    ).scalar())
    settled_order_ids = db.query(MerchantSettlement.order_id).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.source_type == "order",
    )
    historical_unreconciled_count = db.query(Order).filter(
        Order.product_id.in_(product_ids),
        Order.status.in_(["completed", "running", "done"]),
        ~Order.id.in_(settled_order_ids),
    ).count()
    return success({
        "total_revenue": round(total_revenue, 2),
        "pending_amount": round(pending_amount, 2),
        "withdrawn": round(withdrawn, 2),
        "available": max(0, round(available, 6)),
        "today_revenue": today_revenue,
        "historical_unreconciled_count": historical_unreconciled_count,
        "payment_service_enabled": sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED),
    })


@router.get("/rebate")
def supplier_rebate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """商家销售返佣概览"""
    from app.services.reward_entitlements import get_supplier_summary
    return success(get_supplier_summary(user.id, db))


@router.post("/withdraw")
def supplier_withdraw(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Non-mutating tombstone for the old internal fake-arrival path."""
    raise BizError("旧版商家提现已停用，请使用钱包中的人工审核提现申请", status_code=410)


@router.get("/stats")
def supplier_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """数据统计：设备利用率 + 营收趋势"""
    s = _get_supplier(user, db)
    all_products = db.query(Product).filter(Product.supplier_id == s.id).all()
    products = [p for p in all_products if p.status == "on"]
    # 设备利用率
    device_stats = []
    for p in products:
        stock_val = int(p.stock) if p.stock is not None else 0
        order_count = db.query(Order).filter(Order.product_id == p.id).count()
        utilization = min(100, round((order_count / max(stock_val, 1)) * 100, 1)) if stock_val > 0 else 0
        device_stats.append({
            "name": p.name, "gpu_model": p.gpu_model,
            "stock": stock_val, "order_count": order_count,
            "utilization": utilization, "price": float(p.price),
        })
    # 营收趋势（30天按日）
    from datetime import datetime, timedelta, timezone
    from collections import defaultdict
    product_ids = [p.id for p in products]
    if not product_ids:
        product_ids = [0]
    month_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    settlements = db.query(MerchantSettlement).filter(
        MerchantSettlement.supplier_id == s.id,
        MerchantSettlement.status == "settled",
        MerchantSettlement.settled_at >= month_ago,
    ).all()
    daily = defaultdict(float)
    for settlement in settlements:
        day = settlement.settled_at.strftime("%m-%d") if settlement.settled_at else "未知"
        daily[day] += float(settlement.net_amount)
    revenue_trend = [{"date": d, "amount": round(daily[d], 2)} for d in sorted(daily.keys())]
    return success({
        "device_stats": device_stats,
        "revenue_trend": revenue_trend,
        "total_products": len(products),
        "total_orders": len(settlements),
        "attention_count": sum(1 for p in all_products if p.status != "on" or int(p.stock or 0) <= 0),
    })


@router.get("/orders")
def supplier_orders(status_filter: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.routers.order import _order_out, can_deliver_order, is_platform_fulfiller

    platform_operator = is_platform_fulfiller(user)
    supplier = db.query(Supplier).filter(
        Supplier.user_id == user.id,
        Supplier.status == "approved",
    ).first()
    if not supplier and not platform_operator:
        raise BizError("您还不是已审核供应商", status_code=403)
    product_ids = [
        pid for (pid,) in db.query(Product.id).filter(
            Product.supplier_id == supplier.id if supplier else False
        ).all()
    ]
    if platform_operator:
        product_ids.extend(
            # Platform fulfilment is an explicit KAI self-operated boundary.
            # ``source_price`` is shared historical quote metadata and would
            # also admit retired external sources while potentially omitting a
            # valid KAI row with incomplete legacy metadata.
            pid for (pid,) in db.query(Product.id).filter(
                Product.market_source == "kai",
            ).all()
        )
    product_ids = list(set(product_ids))
    if not product_ids:
        product_ids = [0]
    q = db.query(Order).filter(Order.product_id.in_(product_ids))
    if status_filter:
        q = q.filter(Order.status == status_filter)
    items = q.order_by(Order.created_at.desc()).all()
    result = []
    for o in items:
        out = _order_out(o, db)
        out["can_deliver"] = can_deliver_order(o)
        # 加买家信息
        buyer = db.query(User).filter(User.id == o.user_id).first()
        out["buyer_name"] = buyer.username if buyer else "匿名"
        phone = str(buyer.phone or "") if buyer else ""
        out["buyer_phone"] = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else "-"
        result.append(out)
    return success(result)


@router.post("/register")
def register(data: SupplierRegisterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if existing:
        raise BizError("您已提交过入驻申请")
    if not data.company_name or not data.contact or not data.phone:
        raise BizError("请填写完整信息")
    s = Supplier(
        user_id=user.id, company_name=data.company_name, contact=data.contact,
        phone=data.phone, region=data.region, desc=data.desc, status="pending",
    )
    db.add(s)
    user.supplier_status = "pending"
    db.commit()
    db.refresh(s)
    return success(SupplierOut.model_validate(s).model_dump())


@router.get("/mine")
def my_supplier(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not s:
        return success({"status": "not_registered"})
    return success(SupplierOut.model_validate(s).model_dump())


@router.get("/admin/applications")
def admin_list_applications(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    query = db.query(Supplier, User).join(User, User.id == Supplier.user_id)
    if status_filter:
        if status_filter not in {"pending", "approved", "rejected"}:
            raise BizError("商家审核状态无效")
        query = query.filter(Supplier.status == status_filter)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            Supplier.company_name.ilike(pattern),
            Supplier.contact.ilike(pattern),
            Supplier.phone.ilike(pattern),
            User.username.ilike(pattern),
        ))
    total = query.count()
    rows = query.order_by(Supplier.created_at.desc(), Supplier.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return success({
        "items": [
            _admin_application_out(
                supplier,
                applicant,
                identity_verified=_identity_verified(applicant.id, db),
            )
            for supplier, applicant in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    })


@router.post("/admin/applications/{supplier_id}/{action}")
def admin_review_application(
    supplier_id: int,
    action: str,
    data: SupplierReviewIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if action not in {"approve", "reject"}:
        raise BizError("商家审核操作无效")
    if data.version != 1:
        raise BizError("申请资料已更新，请刷新后重试", status_code=409)
    if action == "reject" and len((data.note or "").strip()) < 2:
        raise BizError("驳回时请填写至少 2 个字的原因")
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise BizError("商家入驻申请不存在", status_code=404)
    applicant = db.query(User).filter(User.id == supplier.user_id).first()
    if not applicant:
        raise BizError("申请账号不存在", status_code=404)
    if applicant.id == admin.id:
        raise BizError("管理员不能审核自己的商家申请", status_code=403)
    if supplier.status != "pending":
        raise BizError("该商家入驻申请已完成审核", status_code=409)
    identity_verified = _identity_verified(applicant.id, db)
    if action == "approve" and not identity_verified:
        raise BizError("申请人尚未完成实名认证，不能通过商家审核", status_code=409)
    supplier.status = "approved" if action == "approve" else "rejected"
    applicant.supplier_status = supplier.status
    if action == "reject" and applicant.role == "supplier":
        applicant.role = "personal"
    db.commit()
    db.refresh(supplier)
    db.refresh(applicant)
    return success(_admin_application_out(
        supplier,
        applicant,
        identity_verified=identity_verified,
    ))


@router.put("/profile")
def update_supplier_profile(data: SupplierProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_supplier(user, db)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(s, field, value)
    db.commit()
    return success(SupplierOut.model_validate(s).model_dump())


@router.get("/{sid}")
def store_page(sid: int, db: Session = Depends(get_db)):
    s = db.query(Supplier).filter(Supplier.id == sid, Supplier.status == "approved").first()
    if not s:
        raise BizError("供应商不存在", status_code=404)
    products = db.query(Product).filter(Product.supplier_id == sid, Product.status == "on").limit(20).all()
    from app.routers.product import _product_out
    return success({
        "supplier": _public_supplier_out(s),
        # Pass the session so approved WOD listings retain their real
        # purchasability state on the public merchant page.
        "products": [_product_out(p, db) for p in products],
    })
