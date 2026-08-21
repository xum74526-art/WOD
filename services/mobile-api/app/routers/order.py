import uuid
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.sensitive import protect, reveal
from app.db.session import get_db
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.market_price import MarketSourceStatus
from app.models.order import Order
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.supplier import Supplier
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.order import OrderCreateIn, OrderOut
from app.services.purchase_cycles import available_purchase_cycles
from app.services.market_freshness import product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.product_purchase import product_purchase_availability
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/orders", tags=["order"])


def _platform_fulfillment_user_ids() -> set[int]:
    result: set[int] = set()
    for value in str(settings.PLATFORM_FULFILLMENT_USER_IDS or "").split(","):
        try:
            result.add(int(value.strip()))
        except (TypeError, ValueError):
            continue
    return result


def is_platform_fulfiller(user: User) -> bool:
    return int(user.id) in _platform_fulfillment_user_ids()


_SSH_ACCOUNT_RE = re.compile(
    r"(?P<user>[A-Za-z0-9._-]{1,64})@(?P<host>\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})"
)
_SSH_HOST_RE = re.compile(
    r"(?im)^\s*(?:host|hostname|server|ip|主机|服务器|地址)\s*[:：]\s*"
    r"(?P<host>\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})\s*$"
)
_SSH_USER_RE = re.compile(
    r"(?im)^\s*(?:user|username|login|用户|用户名)\s*[:：]\s*(?P<user>[A-Za-z0-9._-]{1,64})\s*$"
)
_SSH_PORT_RE = re.compile(r"(?im)(?:^|\s)(?:-p\s+|port\s*[:：]\s*|端口\s*[:：]\s*)(?P<port>\d{1,5})(?:\s|$)")


def valid_ssh_info(value: str | None) -> bool:
    """Accept common SSH command or labelled credential formats.

    This is deliberately syntax validation only: connectivity is verified by
    the human fulfilment operator. It prevents empty/free-form notes from
    activating an asset or being exposed as connection credentials.
    """
    plain = str(value or "").strip()
    if not plain or len(plain) > 2000:
        return False
    account = _SSH_ACCOUNT_RE.search(plain)
    host = account.group("host") if account else None
    user = account.group("user") if account else None
    if not host:
        host_match = _SSH_HOST_RE.search(plain)
        user_match = _SSH_USER_RE.search(plain)
        host = host_match.group("host") if host_match else None
        user = user_match.group("user") if user_match else None
    if not host or not user:
        return False
    bare_host = host.strip("[]")
    if bare_host.lower() == "localhost" or "/" in bare_host or ".." in bare_host:
        return False
    if not re.fullmatch(r"[0-9A-Fa-f:.]+|(?:[A-Za-z0-9-]+\.)*[A-Za-z0-9-]+", bare_host):
        return False
    port_match = _SSH_PORT_RE.search(plain)
    if port_match and not 1 <= int(port_match.group("port")) <= 65535:
        return False
    return True


def _same_order_request(order: Order, data: OrderCreateIn) -> bool:
    return (
        int(order.product_id) == int(data.product_id)
        and int(order.quantity or 1) == int(data.quantity)
        and int(order.cycle_days) == int(data.cycle_days)
        and str(order.purchase_type or "usage") == str(data.purchase_type or "usage")
    )


def _ensure_current_market_product(product: Product, db: Session) -> None:
    if product_market_source(product) == "wod":
        return
    now = utcnow()
    states = {
        row.source: source_state(row, now)
        for row in db.query(MarketSourceStatus).all()
        if row.enabled
    }
    state = product_market_state(product, states, now, settings.PRODUCT_OFFER_MAX_AGE_SECONDS)
    if state != "live":
        raise BizError("行情来源暂不可用或报价已过期，请刷新后重试")


def _order_out(o: Order, db: Session) -> dict:
    p = db.query(Product).filter(Product.id == o.product_id).first()
    out = OrderOut.model_validate(o).model_dump()
    ssh_info = reveal(o.ssh_info) or None
    out["ssh_info"] = ssh_info if valid_ssh_info(ssh_info) else None
    out["product_name"] = p.name if p else None
    out["gpu_model"] = p.gpu_model if p else None
    out["market_source"] = product_market_source(p) if p else None
    out["fulfillment_status"] = {
        "paid": "pending_ssh",
        "delivering": "awaiting_confirmation",
        "completed": "active",
        "canceled": "canceled",
    }.get(o.status, o.status)
    a = db.query(Asset).filter(Asset.order_id == o.id).first()
    out["asset_id"] = a.id if a else None
    out["revenue_settlement_enabled"] = settings.REVENUE_SETTLEMENT_ENABLED
    if a:
        total = db.query(Revenue).filter(Revenue.asset_id == a.id).all()
        historical_total = round(sum(float(r.amount) for r in total), 4)
        out["historical_test_revenue"] = historical_total
        out["accumulated_revenue"] = historical_total if settings.REVENUE_SETTLEMENT_ENABLED else 0
    if o.end_at and o.status in ("completed", "running"):
        end = o.end_at.replace(tzinfo=timezone.utc) if o.end_at.tzinfo is None else o.end_at
        out["remaining_days"] = max(0, (end - datetime.now(timezone.utc)).days)
    else:
        out["remaining_days"] = 0
    return out


def _calc_amount(p: Product, cycle_days: int, quantity: int = 1) -> Decimal:
    return Decimal(str(float(p.price) * cycle_days * 24 * quantity)).quantize(Decimal("0.0001"))


@router.post("")
def create_order(data: OrderCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request_id = str(data.client_request_id or "").strip() or None
    if request_id:
        existing = db.query(Order).filter(
            Order.user_id == user.id,
            Order.client_request_id == request_id,
        ).first()
        if existing:
            if not _same_order_request(existing, data):
                raise BizError("重复请求参数不一致，请重新提交", status_code=409)
            return success(_order_out(existing, db))
    p = db.query(Product).filter(
        Product.id == data.product_id, Product.status == "on"
    ).with_for_update().first()
    if not p:
        raise BizError("商品不存在或已下架", status_code=404)
    if p.supplier_id:
        own_supplier = db.query(Supplier).filter(
            Supplier.id == p.supplier_id,
            Supplier.user_id == user.id,
        ).first()
        if own_supplier:
            raise BizError("不能购买自己上架的算力资源", status_code=409)
    purchasable, unavailable_reason = product_purchase_availability(p, db)
    if not purchasable:
        raise BizError(unavailable_reason or "该资源暂不可在 WOD 内下单", status_code=409)
    _ensure_current_market_product(p, db)
    allowed = available_purchase_cycles(p.cycle)
    if data.cycle_days not in allowed:
        raise BizError(f"不支持的周期，可选 {allowed}")
    if data.purchase_type not in ("usage", "holding"):
        raise BizError("不支持的购买模式")
    available_stock = max(int(p.stock or 0), 0)
    if data.quantity > available_stock:
        raise BizError(f"库存不足，当前最多可购买 {available_stock} 台")
    amount = _calc_amount(p, data.cycle_days, data.quantity)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if spendable_wallet_balance(wallet, db) < amount:
        raise BizError("余额不足")

    try:
        # Reserve inventory in the same transaction as the order and wallet
        # update. Cancellation restores it.
        p.stock = available_stock - data.quantity
        now = datetime.now(timezone.utc)
        # Closed-test purchase: reserve the full amount until valid SSH/device
        # delivery is confirmed. No asset exists at checkout.
        wallet.balance = wallet.balance - amount
        wallet.frozen = wallet.frozen + amount
        order = Order(
            order_no="WOD" + datetime.now().strftime("%Y%m%d") + uuid.uuid4().hex[:8].upper(),
            client_request_id=request_id,
            user_id=user.id, product_id=p.id, quantity=data.quantity, cycle_days=data.cycle_days,
            amount=amount, status="paid", purchase_type=data.purchase_type,
            start_at=now, end_at=None,
        )
        db.add(order)
        db.flush()
        db.add(Ledger(
            user_id=user.id, wallet_id=wallet.id, type="freeze", direction="out",
            amount=amount, balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=order.id,
            remark=f"购买{'持有' if data.purchase_type == 'holding' else '使用'} {p.name} × {data.quantity}（待交付）",
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Order).filter(
            Order.user_id == user.id,
            Order.client_request_id == request_id,
        ).first() if request_id else None
        if existing and _same_order_request(existing, data):
            return success(_order_out(existing, db))
        raise BizError("下单失败，请重试")
    except Exception:
        db.rollback()
        raise BizError("下单失败，请重试")
    db.refresh(order)
    return success(_order_out(order, db))


@router.post("/{oid}/deliver")
def deliver_ssh(oid: int, data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == oid).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    # WOD listings are fulfilled by their owning approved merchant. Provider-
    # backed closed-test orders are visible only to explicitly configured
    # platform fulfilment operators.
    p = db.query(Product).filter(Product.id == o.product_id).first()
    if not p:
        raise BizError("商品不存在", status_code=404)
    if product_market_source(p) == "wod":
        s = db.query(Supplier).filter(Supplier.user_id == user.id).first()
        authorized = bool(s and s.status == "approved" and int(p.supplier_id or 0) == s.id)
    else:
        authorized = is_platform_fulfiller(user)
    if not authorized:
        raise BizError("无权操作此订单", status_code=403)
    if o.status != "paid":
        raise BizError("当前订单状态不可交付")
    ssh_info = str(data.get("ssh_info", "")).strip()
    if not valid_ssh_info(ssh_info):
        raise BizError("SSH 信息格式无效，请填写用户名、主机地址及有效端口")
    o.ssh_info = protect(ssh_info)
    o.status = "delivering"
    db.commit()
    return success({"id": oid, "status": "delivering"})


@router.post("/{oid}/confirm")
def confirm_delivery(oid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == oid, Order.user_id == user.id).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    if o.status != "delivering":
        raise BizError("当前订单状态不可确认")
    ssh_info = reveal(o.ssh_info)
    if not valid_ssh_info(ssh_info):
        raise BizError("SSH 连接信息无效，请联系交付人员重新填写", status_code=409)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if wallet.frozen < o.amount:
        raise BizError("订单冻结余额异常，请联系测试负责人核查", status_code=409)
    wallet.frozen = wallet.frozen - o.amount
    now = datetime.now(timezone.utc)
    o.status = "completed"
    o.start_at = now
    o.end_at = now + timedelta(days=o.cycle_days)
    payment_entry = db.query(Ledger).filter(
        Ledger.ref_order_id == o.id,
        Ledger.type.in_(["freeze", "pay"]),
    ).order_by(Ledger.id.asc()).first()
    if payment_entry:
        payment_entry.type = "pay"
        payment_entry.remark = f"购买{'持有' if o.purchase_type == 'holding' else '使用'}·已确认交付({o.order_no})"
        payment_entry.balance_after = spendable_wallet_balance(wallet, db)
    else:
        db.add(Ledger(
            user_id=user.id, wallet_id=wallet.id, type="pay", direction="out",
            amount=o.amount, balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=o.id,
            remark=f"购买{'持有' if o.purchase_type == 'holding' else '使用'}·已确认交付({o.order_no})",
        ))
    # SSH 交付证明使用权，不代表平台已接入真实算力收益结算。
    daily_rate = Decimal("0")
    # Consumer rebates are derived from the confirmed order amount and the
    # user's current monthly tier.  Closed-test rewards are card-hours only.
    p = db.query(Product).filter(Product.id == o.product_id).first()
    from app.services.rebate_settle import estimate_completed_order_rebate
    from app.services.reward_program import reward_program_enabled
    program_enabled = reward_program_enabled()
    reward_eligible = bool(program_enabled and o.purchase_type == "usage")
    db.flush()
    est_rebate = float(estimate_completed_order_rebate(o, db)) if reward_eligible else 0
    quantity = max(int(o.quantity or 1), 1)
    unit_value = (Decimal(o.amount) / Decimal(quantity)).quantize(Decimal("0.0001"))
    asset = Asset(
        user_id=user.id, product_id=o.product_id, order_id=o.id,
        quantity=quantity, value=unit_value, daily_rate=daily_rate, status="active",
        start_at=now, end_at=o.end_at,
        purchase_type=o.purchase_type or "usage",
        rebate_status="pending" if reward_eligible else None,
        rebate_amount=est_rebate,
    )
    db.add(asset)

    # Invite and merchant rewards join the same transaction as delivery
    # confirmation.  Repeating a service call for the same order is harmless.
    from app.routers.invite import process_first_order_reward
    if program_enabled:
        process_first_order_reward(o.user_id, o.id, db)
    from app.services.supplier_rebate import process_supplier_rebate
    if program_enabled and p and p.supplier_id:
        from app.models.supplier import Supplier
        s = db.query(Supplier).filter(Supplier.id == p.supplier_id).first()
        if s:
            process_supplier_rebate(s.user_id, o.id, db)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise BizError("确认交付失败，请重试")
    return success({"id": oid, "status": "completed"})


@router.get("")
def list_orders(status_filter: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.user_id == user.id)
    if status_filter:
        q = q.filter(Order.status == status_filter)
    items = q.order_by(Order.created_at.desc()).all()
    return success([_order_out(o, db) for o in items])


@router.get("/{oid}")
def order_detail(oid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == oid, Order.user_id == user.id).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    return success(_order_out(o, db))


@router.post("/{oid}/renew")
def renew_order(oid: int, data: OrderCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == oid, Order.user_id == user.id).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    if o.status not in ("completed", "running"):
        raise BizError("当前订单不可续费")
    if o.purchase_type != "usage":
        raise BizError("持有交易与二级市场尚未接入，历史持有订单不可续费", status_code=503)
    p = db.query(Product).filter(Product.id == o.product_id).first()
    if not p:
        raise BizError("商品不存在或已下架", status_code=404)
    purchasable, unavailable_reason = product_purchase_availability(p, db)
    if not purchasable:
        raise BizError(unavailable_reason or "该资源暂不可在 WOD 内续费", status_code=409)
    _ensure_current_market_product(p, db)
    allowed = available_purchase_cycles(p.cycle)
    if data.cycle_days not in allowed:
        raise BizError(f"不支持的周期，可选 {allowed}")
    quantity = max(int(o.quantity or 1), 1)
    unit_amount = _calc_amount(p, data.cycle_days)
    amount = _calc_amount(p, data.cycle_days, quantity)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if spendable_wallet_balance(wallet, db) < amount:
        raise BizError("余额不足")
    a = db.query(Asset).filter(Asset.order_id == o.id).first()
    try:
        wallet.balance = wallet.balance - amount
        now = datetime.now(timezone.utc)
        base = o.end_at or now
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        new_end = base + timedelta(days=data.cycle_days)
        o.end_at = new_end
        o.amount = o.amount + amount
        o.cycle_days = o.cycle_days + data.cycle_days
        o.status = "running"
        if a:
            a.end_at = new_end
            a.status = "active"
            a.value = a.value + unit_amount
        db.add(Ledger(
            user_id=user.id, wallet_id=wallet.id, type="pay", direction="out",
            amount=amount, balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=o.id, remark=f"续费 {p.name} × {quantity}",
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise BizError("续费失败，请重试")
    db.refresh(o)
    return success(_order_out(o, db))


@router.post("/{oid}/cancel")
def cancel_order(oid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == oid, Order.user_id == user.id).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    if o.status != "paid":
        raise BizError("当前订单不可取消")
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if wallet.frozen < o.amount:
        raise BizError("订单冻结余额异常，请联系测试负责人核查", status_code=409)
    a = db.query(Asset).filter(Asset.order_id == o.id).first()
    try:
        refund = Decimal(str(o.amount))
        # 使用模式下资金在冻结中，取消需解冻退回余额
        wallet.frozen = wallet.frozen - refund
        wallet.balance = wallet.balance + refund
        o.status = "canceled"
        product = db.query(Product).filter(Product.id == o.product_id).with_for_update().first()
        if product:
            product.stock = max(int(product.stock or 0), 0) + max(int(o.quantity or 1), 1)
        if a:
            a.status = "expired"
        db.add(Ledger(
            user_id=user.id, wallet_id=wallet.id, type="refund", direction="in",
            amount=refund, balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=o.id, remark=f"取消订单 {o.order_no} 退款",
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise BizError("取消失败，请重试")
    db.refresh(o)
    return success(_order_out(o, db))
