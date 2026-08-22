import uuid
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_platform, get_current_user
from app.core.sensitive import protect, reveal
from app.db.session import get_db
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.market_price import MarketSourceStatus
from app.models.order import Order
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.supplier import Supplier
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.order import OrderCreateIn, OrderOut, OrderRenewIn
from app.services.purchase_cycles import available_purchase_cycles, valid_purchase_hours
from app.services.auth_session import PLATFORMS
from app.services.market_freshness import product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.product_purchase import product_purchase_availability
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/orders", tags=["order"])

_RENEW_LOCK = Lock()
RENEWABLE_ORDER_STATUSES = {"completed", "running"}


def _trusted_platform(value: object) -> str:
    """Normalize direct service/test calls; HTTP values come from AuthSession."""

    return value if isinstance(value, str) and value in PLATFORMS else "legacy"


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
    duration_matches = (
        int(order.purchase_hours) == int(data.hours) and data.cycle_days is None
        if order.purchase_hours is not None and data.hours is not None
        else order.purchase_hours is None
        and data.hours is None
        and int(order.cycle_days) == int(data.cycle_days if data.cycle_days is not None else 30)
    )
    return (
        int(order.product_id) == int(data.product_id)
        and int(order.quantity or 1) == int(data.quantity)
        and duration_matches
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
    market_source = product_market_source(p) if p else None
    out["market_source"] = market_source
    out["billing_unit"] = "GPU_HOUR"
    out["amount_card_hours"] = float(o.amount)
    # Reconstruct the effective booked unit price from the immutable order
    # amount.  Reading today's Product.price here would silently reinterpret a
    # historical order whenever KAI publishes a new quote.
    if o.purchase_hours is not None and int(o.purchase_hours) > 0:
        quantity = max(int(o.quantity or 1), 1)
        rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
        booked_price = (
            Decimal(o.amount) * rate / Decimal(int(o.purchase_hours) * quantity)
            if rate > 0 else None
        )
        out["price_cny_per_gpu_hour"] = (
            float(booked_price.quantize(Decimal("0.000001"))) if booked_price is not None else None
        )
    else:
        out["price_cny_per_gpu_hour"] = None
    if o.purchase_hours is not None:
        out["cycle_days"] = None
        out["duration_hours"] = int(o.purchase_hours)
        out["purchase_unit"] = "hour"
    else:
        out["duration_hours"] = None
        out["purchase_unit"] = "day"
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
        remaining_seconds = max((end - datetime.now(timezone.utc)).total_seconds(), 0)
        if o.purchase_hours is not None:
            out["remaining_days"] = None
            out["remaining_hours"] = int((remaining_seconds + 3599) // 3600)
        else:
            out["remaining_days"] = max(0, int(remaining_seconds // 86400))
            out["remaining_hours"] = None
    else:
        out["remaining_days"] = None if o.purchase_hours is not None else 0
        out["remaining_hours"] = 0 if o.purchase_hours is not None else None
    return out


def _calc_legacy_day_amount(p: Product, cycle_days: int, quantity: int = 1) -> Decimal:
    return Decimal(str(float(p.price) * cycle_days * 24 * quantity)).quantize(Decimal("0.0001"))


def _calc_kai_hour_amount(p: Product, hours: int, quantity: int = 1) -> Decimal:
    """Convert KAI's CNY/GPU-hour quote into wallet card-hours."""
    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
    if rate <= 0:
        raise BizError("卡时兑换率配置无效，请联系管理员", status_code=503)
    return (
        Decimal(str(p.price)) * Decimal(hours) * Decimal(quantity) / rate
    ).quantize(Decimal("0.0001"))


def _begin_renewal_transaction(db: Session) -> None:
    """Use a database write lock on SQLite; row locks handle other databases."""

    if db.get_bind().dialect.name != "sqlite":
        return
    # Authentication performs read queries before entering the endpoint. Close
    # that read-only transaction so BEGIN IMMEDIATE can serialize all renewal
    # reads and writes across SQLite connections/processes.
    if db.in_transaction():
        db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))


def _same_renewal_request(event: OrderRenewal, oid: int, data: OrderRenewIn) -> bool:
    return (
        int(event.order_id) == int(oid)
        and (int(event.purchase_hours) if event.purchase_hours is not None else None) == data.hours
        and (int(event.cycle_days) if event.cycle_days is not None else None) == data.cycle_days
    )


def _stored_renewal_response(event: OrderRenewal) -> dict:
    return dict(event.response_payload or {})


@router.post("")
def create_order(
    data: OrderCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    platform = _trusted_platform(platform)
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
    source = product_market_source(p)
    purchase_hours: int | None = None
    cycle_days = 0
    if source == "kai":
        if data.cycle_days is not None:
            raise BizError("KAI 算力仅支持按小时购买，请提交 hours", status_code=422)
        if not valid_purchase_hours(data.hours):
            raise BizError("购买时长必须是 1 至 720 的整数小时", status_code=422)
        purchase_hours = int(data.hours)
    else:
        if data.hours is not None:
            raise BizError("该历史日周期商品不支持小时参数", status_code=422)
        cycle_days = int(data.cycle_days if data.cycle_days is not None else 30)
        allowed = available_purchase_cycles(p.cycle)
        if cycle_days not in allowed:
            raise BizError(f"不支持的周期，可选 {allowed}")
    if data.purchase_type not in ("usage", "holding"):
        raise BizError("不支持的购买模式")
    reserved_stock = max(int(p.stock or 0), 0)
    available_stock = reserved_stock
    if source == "kai":
        if p.platform_stock_cap is not None:
            reserved_stock = min(reserved_stock, max(int(p.platform_stock_cap), 0))
        # The upstream option is only a per-order configuration ceiling.  It
        # limits this checkout but must not mint or consume platform stock.
        source_order_limit = max(int(p.source_max_configurable_quantity or 0), 0)
        available_stock = min(reserved_stock, source_order_limit)
    if data.quantity > available_stock:
        raise BizError(f"库存不足，当前最多可购买 {available_stock} 台")
    amount = (
        _calc_kai_hour_amount(p, purchase_hours, data.quantity)
        if purchase_hours is not None
        else _calc_legacy_day_amount(p, cycle_days, data.quantity)
    )
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if spendable_wallet_balance(wallet, db) < amount:
        raise BizError("余额不足")

    try:
        # Reserve inventory in the same transaction as the order and wallet
        # update. Cancellation restores it.
        p.stock = reserved_stock - data.quantity
        now = datetime.now(timezone.utc)
        # Manually fulfilled purchase: reserve the full amount until valid SSH/device
        # delivery is confirmed. No asset exists at checkout.
        wallet.balance = wallet.balance - amount
        wallet.frozen = wallet.frozen + amount
        order = Order(
            order_no="WOD" + datetime.now().strftime("%Y%m%d") + uuid.uuid4().hex[:8].upper(),
            client_request_id=request_id,
            user_id=user.id, product_id=p.id, quantity=data.quantity,
            cycle_days=cycle_days, purchase_hours=purchase_hours,
            created_platform=platform, last_modified_platform=platform,
            amount=amount, status="paid", purchase_type=data.purchase_type,
            start_at=now, end_at=None,
        )
        db.add(order)
        db.flush()
        db.add(Ledger(
            user_id=user.id, wallet_id=wallet.id, type="freeze", direction="out",
            amount=amount, balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=order.id,
            remark=(
                f"购买{'持有' if data.purchase_type == 'holding' else '使用'} {p.name} × {data.quantity}"
                f"（{purchase_hours}小时，待交付）"
                if purchase_hours is not None
                else f"购买{'持有' if data.purchase_type == 'holding' else '使用'} {p.name} × {data.quantity}（待交付）"
            ),
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
def deliver_ssh(
    oid: int,
    data: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    o = db.query(Order).filter(Order.id == oid).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    # WOD listings are fulfilled by their owning approved merchant. KAI-backed
    # manually delivered orders are visible only to explicitly configured
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
    o.last_modified_platform = _trusted_platform(platform)
    db.commit()
    return success({"id": oid, "status": "delivering"})


@router.post("/{oid}/confirm")
def confirm_delivery(
    oid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
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
        raise BizError("订单冻结余额异常，请联系平台服务人员核查", status_code=409)
    wallet.frozen = wallet.frozen - o.amount
    now = datetime.now(timezone.utc)
    o.status = "completed"
    o.last_modified_platform = _trusted_platform(platform)
    o.start_at = now
    o.end_at = (
        now + timedelta(hours=o.purchase_hours)
        if o.purchase_hours is not None
        else now + timedelta(days=o.cycle_days)
    )
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
    # user's current monthly tier. In-app rewards are card-hours only.
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
def renew_order(
    oid: int,
    data: OrderRenewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    request_id = str(data.client_request_id or "").strip()
    if not 12 <= len(request_id) <= 64:
        raise BizError("续费请求编号长度必须为 12 至 64 个字符", status_code=422)
    user_id = int(user.id)
    platform = _trusted_platform(platform)

    # PostgreSQL/MySQL use row-level FOR UPDATE locks below. SQLite ignores
    # FOR UPDATE, so the process lock complements BEGIN IMMEDIATE and also
    # keeps in-memory test databases deterministic.
    with _RENEW_LOCK:
        try:
            _begin_renewal_transaction(db)
            o = db.query(Order).filter(
                Order.id == oid, Order.user_id == user_id,
            ).with_for_update().first()
            if not o:
                raise BizError("订单不存在", status_code=404)

            existing = db.query(OrderRenewal).filter(
                OrderRenewal.user_id == user_id,
                OrderRenewal.client_request_id == request_id,
            ).with_for_update().first()
            if existing:
                if not _same_renewal_request(existing, oid, data):
                    raise BizError("重复续费请求参数不一致，请重新提交", status_code=409)
                payload = _stored_renewal_response(existing)
                db.commit()
                return success(payload)

            if o.status not in RENEWABLE_ORDER_STATUSES:
                raise BizError("当前订单不可续费，仅已交付或运行中的使用订单可续费", status_code=409)
            if o.purchase_type != "usage":
                raise BizError("持有交易与二级市场尚未接入，历史持有订单不可续费", status_code=503)
            p = db.query(Product).filter(Product.id == o.product_id).first()
            if not p:
                raise BizError("商品不存在或已下架", status_code=404)
            purchasable, unavailable_reason = product_purchase_availability(p, db)
            if not purchasable:
                raise BizError(unavailable_reason or "该资源暂不可在 WOD 内续费", status_code=409)
            _ensure_current_market_product(p, db)
            quantity = max(int(o.quantity or 1), 1)
            if o.purchase_hours is not None:
                if data.cycle_days is not None or not valid_purchase_hours(data.hours):
                    raise BizError("该订单仅支持按 1 至 720 的整数小时续费", status_code=422)
                renewal_hours = int(data.hours)
                renewal_days = None
                unit_amount = _calc_kai_hour_amount(p, renewal_hours)
                amount = _calc_kai_hour_amount(p, renewal_hours, quantity)
            else:
                if data.hours is not None or data.cycle_days is None:
                    raise BizError("历史日周期订单仅支持 cycle_days 参数", status_code=422)
                renewal_days = int(data.cycle_days)
                allowed = available_purchase_cycles(p.cycle)
                if renewal_days not in allowed:
                    raise BizError(f"不支持的周期，可选 {allowed}")
                renewal_hours = None
                unit_amount = _calc_legacy_day_amount(p, renewal_days)
                amount = _calc_legacy_day_amount(p, renewal_days, quantity)

            wallet = db.query(Wallet).filter(
                Wallet.user_id == user_id,
            ).with_for_update().first()
            if not wallet:
                raise BizError("钱包不存在", status_code=404)
            if spendable_wallet_balance(wallet, db) < amount:
                raise BizError("余额不足")

            now = datetime.now(timezone.utc)
            previous_end = o.end_at
            comparable_end = previous_end or now
            if comparable_end.tzinfo is None:
                comparable_end = comparable_end.replace(tzinfo=timezone.utc)
            base = max(now, comparable_end)
            new_end = (
                base + timedelta(hours=renewal_hours)
                if renewal_hours is not None
                else base + timedelta(days=renewal_days)
            )
            renewal = OrderRenewal(
                order_id=o.id,
                user_id=user_id,
                client_request_id=request_id,
                created_platform=platform,
                purchase_hours=renewal_hours,
                cycle_days=renewal_days,
                quantity=quantity,
                amount=amount,
                previous_end_at=previous_end,
                new_end_at=new_end,
                total_amount_after=Decimal(o.amount) + amount,
                total_purchase_hours_after=(
                    int(o.purchase_hours or 0) + renewal_hours if renewal_hours is not None else None
                ),
                total_cycle_days_after=(
                    int(o.cycle_days or 0) + renewal_days if renewal_days is not None else None
                ),
                response_payload={},
            )
            db.add(renewal)
            db.flush()  # claim the unique idempotency key before any balance mutation

            wallet.balance = wallet.balance - amount
            o.end_at = new_end
            o.amount = renewal.total_amount_after
            o.last_modified_platform = platform
            if renewal_hours is not None:
                o.purchase_hours = renewal.total_purchase_hours_after
            else:
                o.cycle_days = renewal.total_cycle_days_after
            o.status = "running"
            asset = db.query(Asset).filter(Asset.order_id == o.id).with_for_update().first()
            if asset:
                asset.end_at = new_end
                asset.status = "active"
                asset.value = asset.value + unit_amount
            db.add(Ledger(
                user_id=user_id,
                wallet_id=wallet.id,
                type="pay",
                direction="out",
                amount=amount,
                balance_after=spendable_wallet_balance(wallet, db),
                ref_order_id=None,
                ref_order_renewal_id=renewal.id,
                event_key=f"order_renewal:{renewal.id}",
                remark=f"续费 {p.name} × {quantity} ({request_id})",
            ))
            db.flush()
            payload = _order_out(o, db)
            payload.update({
                "renewal_id": renewal.id,
                "renewal_client_request_id": request_id,
                "renewal_amount_card_hours": float(amount),
                "renewal_purchase_hours": renewal_hours,
                "renewal_cycle_days": renewal_days,
                "renewal_previous_end_at": previous_end,
                "renewal_new_end_at": new_end,
            })
            renewal.response_payload = jsonable_encoder(payload)
            db.commit()
            return success(_stored_renewal_response(renewal))
        except BizError:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            existing = db.query(OrderRenewal).filter(
                OrderRenewal.user_id == user_id,
                OrderRenewal.client_request_id == request_id,
            ).first()
            if existing and _same_renewal_request(existing, oid, data):
                return success(_stored_renewal_response(existing))
            raise BizError("续费请求冲突，请更换请求编号后重试", status_code=409)
        except Exception:
            db.rollback()
            raise BizError("续费失败，请重试")


@router.post("/{oid}/cancel")
def cancel_order(
    oid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    o = db.query(Order).filter(
        Order.id == oid, Order.user_id == user.id,
    ).with_for_update().first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    if o.status != "paid":
        raise BizError("当前订单不可取消")
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if wallet.frozen < o.amount:
        raise BizError("订单冻结余额异常，请联系平台服务人员核查", status_code=409)
    a = db.query(Asset).filter(Asset.order_id == o.id).first()
    try:
        refund = Decimal(str(o.amount))
        # 使用模式下资金在冻结中，取消需解冻退回余额
        wallet.frozen = wallet.frozen - refund
        wallet.balance = wallet.balance + refund
        o.status = "canceled"
        o.last_modified_platform = _trusted_platform(platform)
        product = db.query(Product).filter(Product.id == o.product_id).with_for_update().first()
        if product:
            restored_stock = max(int(product.stock or 0), 0) + max(int(o.quantity or 1), 1)
            if product_market_source(product) == "kai" and product.platform_stock_cap is not None:
                restored_stock = min(restored_stock, max(int(product.platform_stock_cap), 0))
            product.stock = restored_stock
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
