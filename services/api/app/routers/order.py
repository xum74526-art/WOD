import uuid
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_platform, get_current_user, require_admin
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
from app.schemas.order import (
    OrderCreateIn,
    OrderDisputeIn,
    OrderDisputeResolveIn,
    OrderDeliverIn,
    OrderOut,
    OrderRenewIn,
)
from app.services.purchase_cycles import available_purchase_cycles, valid_purchase_hours
from app.services.auth_session import PLATFORMS
from app.services.market_freshness import product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.product_purchase import product_purchase_availability
from app.services.product_provider import product_provider_info
from app.services.merchant_settlement import settle_merchant_sale
from app.services.reward_entitlements import (
    create_consumer_order_accrual,
    create_consumer_renewal_accrual,
    create_supplier_order_accrual,
    create_supplier_renewal_accrual,
)
from app.services.wallet_balance import spendable_wallet_balance
from app.services.funding_allocation import (
    capture_order_funding,
    refund_order_funding,
    reserve_order_funding,
    spend_renewal_funding,
)
from app.services.invite_rewards_v2 import (
    process_invite_order_event,
    process_invite_renewal_event,
)
from app.services.holding_trade import HOLDING_LIFECYCLE_POLICY
from app.services.trade_mode import require_direct_trade_enabled, require_holding_trade_enabled
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/orders", tags=["order"])

_RENEW_LOCK = Lock()
RENEWABLE_ORDER_STATUSES = {"completed", "running"}
UNIT_PRICE_QUANTUM = Decimal("0.0001")


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


def can_deliver_order(order: Order, *, now: datetime | None = None) -> bool:
    """Return the backend-owned seller action state for a pending order."""

    if order.status != "paid":
        return False
    current = now or datetime.now(timezone.utc)
    due = order.delivery_due_at
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due is None or due > current


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
    out["ssh_info"] = (
        ssh_info
        if o.status not in ("canceled", "paid") and valid_ssh_info(ssh_info)
        else None
    )
    out["product_name"] = p.name if p else None
    out["gpu_model"] = p.gpu_model if p else None
    market_source = product_market_source(p) if p else None
    out["market_source"] = market_source
    if p:
        out.update(product_provider_info(p, db))
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
        "running": "active",
        "done": "expired",
        "disputed": "under_review",
        "canceled": "canceled",
    }.get(o.status, o.status)
    out["can_cancel"] = o.status == "paid"
    out["can_confirm"] = o.status == "delivering"
    out["can_deliver"] = False
    out["can_renew"] = bool(
        p
        and o.status in RENEWABLE_ORDER_STATUSES
        and o.purchase_type == "usage"
        and not (market_source == "wod" and o.purchase_hours is not None)
    )
    confirmation_due = o.confirmation_due_at
    if confirmation_due is not None and confirmation_due.tzinfo is None:
        confirmation_due = confirmation_due.replace(tzinfo=timezone.utc)
    out["can_dispute"] = (
        o.status == "delivering"
        and (confirmation_due is None or confirmation_due > datetime.now(timezone.utc))
    )
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
    elif o.purchase_type == "holding":
        out["remaining_days"] = None
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


def _calc_merchant_hour_amount(p: Product, hours: int, quantity: int = 1) -> Decimal:
    """Charge a merchant's card-hour/GPU-hour listing without CNY conversion."""

    return (
        Decimal(str(p.price)) * Decimal(hours) * Decimal(quantity)
    ).quantize(Decimal("0.0001"))


def _normalized_unit_price(value: object) -> Decimal:
    return Decimal(str(value)).quantize(UNIT_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _current_unit_price_card_hours(product: Product, source: str) -> Decimal:
    if source == "kai":
        rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
        if rate <= 0:
            raise BizError("卡时兑换率配置无效，请联系管理员", status_code=503)
        return _normalized_unit_price(Decimal(str(product.price)) / rate)
    return _normalized_unit_price(product.price)


def _validate_expected_unit_price(
    product: Product,
    source: str,
    expected: Decimal | None,
) -> None:
    """Reject a stale checkout before inventory or wallet funds are touched."""

    if source == "wod":
        if expected is None:
            raise BizError("请确认当前商品单价后再下单", status_code=422)
        current = _current_unit_price_card_hours(product, source)
    elif source == "kai" and expected is not None:
        current = _current_unit_price_card_hours(product, source)
    else:
        return
    if _normalized_unit_price(expected) != current:
        raise BizError("价格已更新，请刷新后重新确认", status_code=409)


def _product_snapshot(product: Product, source: str, db: Session) -> dict:
    provider = product_provider_info(product, db)
    return {
        "product_name": product.name,
        "gpu_model": product.gpu_model,
        "memory": product.memory,
        "region_code": product.region_code,
        "region_name": product.region_name,
        "city": product.city,
        "confirmed_unit_price_card_hours": format(
            _current_unit_price_card_hours(product, source), "f"
        ),
        "seller_id": product.supplier_id,
        "seller_type": provider["seller_type"],
        "seller_name": provider["seller_name"],
        "market_source": source,
        "external_product_id": product.external_product_id,
        "price_observed_at": product.price_updated_at.isoformat() if product.price_updated_at else None,
    }


def _begin_serialized_write_transaction(db: Session) -> None:
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
    require_direct_trade_enabled()
    platform = _trusted_platform(platform)
    # SQLite ignores FOR UPDATE. Serializing before the stock and wallet reads
    # prevents two concurrent checkouts from selling the last unit twice or
    # spending the same in-app card-hours twice.
    _begin_serialized_write_transaction(db)
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
    source = product_market_source(p)
    holding_purchase = data.purchase_type == "holding"
    # Holding is an immediate KAI-quote asset acquisition; it does not require
    # an SSH fulfilment operator. Usage checkout keeps the stricter fulfilment
    # readiness check unchanged.
    if not (holding_purchase and source == "kai"):
        purchasable, unavailable_reason = product_purchase_availability(p, db)
        if not purchasable:
            raise BizError(unavailable_reason or "该资源暂不可在KAI星算内下单", status_code=409)
    _ensure_current_market_product(p, db)
    _validate_expected_unit_price(p, source, data.expected_unit_price_card_hours)
    product_snapshot = _product_snapshot(p, source, db)
    purchase_hours: int | None = None
    cycle_days = 0
    if source == "kai":
        if data.cycle_days is not None:
            raise BizError("KAI 算力仅支持按小时购买，请提交 hours", status_code=422)
        if not valid_purchase_hours(data.hours):
            raise BizError("购买时长必须是 1 至 720 的整数小时", status_code=422)
        purchase_hours = int(data.hours)
    elif source == "wod" and data.hours is not None:
        if data.cycle_days is not None:
            raise BizError("按小时购买时不能同时提交日周期", status_code=422)
        if not valid_purchase_hours(data.hours):
            raise BizError("购买时长必须是 1 至 720 的整数小时", status_code=422)
        purchase_hours = int(data.hours)
    else:
        # Compatibility for already-published clients that explicitly submit a
        # legacy day cycle.  New merchant product responses advertise hours.
        if data.cycle_days is None:
            raise BizError("购买时长必须是 1 至 720 的整数小时", status_code=422)
        cycle_days = int(data.cycle_days)
        allowed = available_purchase_cycles(p.cycle)
        if cycle_days not in allowed:
            raise BizError(f"不支持的周期，可选 {allowed}")
    if holding_purchase:
        require_holding_trade_enabled()
        if source != "kai" or p.supplier_id is not None:
            raise BizError("持有模式仅支持 KAI 自营且具备有效行情的算力资源", status_code=409)
        if data.expected_unit_price_card_hours is None:
            raise BizError("请确认当前持有买入单价后再下单", status_code=422)
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
        if purchase_hours is not None and source == "kai"
        else _calc_merchant_hour_amount(p, purchase_hours, data.quantity)
        if purchase_hours is not None and source == "wod"
        else _calc_legacy_day_amount(p, cycle_days, data.quantity)
    )
    if amount <= 0:
        raise BizError("订单金额无效，请刷新后重试", status_code=409)
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
        # Usage orders reserve funds until valid SSH delivery is confirmed.
        # A holding order is a card-hour-denominated asset acquisition and is
        # therefore captured and registered immediately without SSH delivery.
        order = Order(
            order_no="WOD" + datetime.now().strftime("%Y%m%d") + uuid.uuid4().hex[:8].upper(),
            client_request_id=request_id,
            user_id=user.id, product_id=p.id, quantity=data.quantity,
            cycle_days=cycle_days, purchase_hours=purchase_hours,
            created_platform=platform, last_modified_platform=platform,
            amount=amount, status="completed" if holding_purchase else "paid", purchase_type=data.purchase_type,
            product_snapshot=product_snapshot,
            lifecycle_policy_version=HOLDING_LIFECYCLE_POLICY if holding_purchase else "reserved-v1",
            start_at=now, end_at=None,
            delivery_due_at=None if holding_purchase else now + timedelta(
                hours=max(int(settings.ORDER_DELIVERY_TIMEOUT_HOURS), 1)
            ),
            confirmed_at=now if holding_purchase else None,
        )
        db.add(order)
        db.flush()
        reserve_order_funding(order, wallet, amount, db)
        if holding_purchase:
            capture_order_funding(order, wallet, db, captured_at=now)
            unit_value = (amount / Decimal(max(int(data.quantity), 1))).quantize(Decimal("0.0001"))
            db.add(Asset(
                user_id=user.id,
                product_id=p.id,
                order_id=order.id,
                quantity=data.quantity,
                value=unit_value,
                daily_rate=Decimal("0"),
                status="active",
                purchase_type="holding",
                start_at=now,
                end_at=None,
                rebate_status=None,
                rebate_amount=0,
            ))
            db.add(Ledger(
                user_id=user.id,
                wallet_id=wallet.id,
                type="pay",
                direction="out",
                amount=amount,
                balance_after=spendable_wallet_balance(wallet, db),
                ref_order_id=order.id,
                event_key=f"holding_asset_buy:{order.id}",
                remark=f"购买持有资产 {p.name} × {data.quantity}（{purchase_hours} GPU 小时）",
            ))
        else:
            db.add(Ledger(
                user_id=user.id, wallet_id=wallet.id, type="freeze", direction="out",
                amount=amount, balance_after=spendable_wallet_balance(wallet, db),
                ref_order_id=order.id,
                remark=(
                    f"购买使用 {p.name} × {data.quantity}"
                    f"（{purchase_hours}小时，待交付）"
                    if purchase_hours is not None
                    else f"购买使用 {p.name} × {data.quantity}（待交付）"
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
    data: OrderDeliverIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    o = db.query(Order).filter(Order.id == oid).first()
    if not o:
        raise BizError("订单不存在", status_code=404)
    # ZTW-branded listings are fulfilled by their owning approved merchant. KAI-backed
    # manually delivered orders are visible only to explicitly configured
    # platform fulfilment operators.
    p = db.query(Product).filter(Product.id == o.product_id).first()
    if not p:
        raise BizError("商品不存在", status_code=404)
    source = product_market_source(p)
    if source == "wod":
        s = db.query(Supplier).filter(Supplier.user_id == user.id).first()
        authorized = bool(s and s.status == "approved" and int(p.supplier_id or 0) == s.id)
    elif source == "kai":
        authorized = is_platform_fulfiller(user)
    else:
        # Retired quote sources are audit-only and cannot be revived through
        # the manual delivery endpoint, even by a platform fulfiller.
        authorized = False
    if not authorized:
        raise BizError("无权操作此订单", status_code=403)
    ssh_info = data.ssh_info
    if not valid_ssh_info(ssh_info):
        raise BizError("SSH 信息格式无效，请填写用户名、主机地址及有效端口")
    now = datetime.now(timezone.utc)
    changed = db.query(Order).filter(
        Order.id == oid,
        Order.status == "paid",
        or_(Order.delivery_due_at.is_(None), Order.delivery_due_at > now),
    ).update({
        Order.ssh_info: protect(ssh_info),
        Order.status: "delivering",
        Order.delivered_at: now,
        Order.confirmation_due_at: now + timedelta(
            hours=max(int(settings.ORDER_CONFIRMATION_TIMEOUT_HOURS), 1)
        ),
        Order.last_modified_platform: _trusted_platform(platform),
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("当前订单状态不可交付", status_code=409)
    db.commit()
    db.expire_all()
    current = db.query(Order).filter(Order.id == oid).populate_existing().first()
    return success(_order_out(current, db))


def _complete_reserved_order(
    order: Order,
    db: Session,
    *,
    platform: str,
    allowed_statuses: tuple[str, ...] = ("delivering",),
    resolved_by: int | None = None,
    resolution_note: str | None = None,
) -> bool:
    """Atomically release reserved funds and create all sale-side facts."""

    current_status = db.query(Order.status).filter(Order.id == order.id).scalar()
    if current_status in ("completed", "running", "done"):
        return False
    original_status = str(current_status)
    changed = db.query(Order).filter(
        Order.id == order.id,
        Order.status.in_(allowed_statuses),
    ).update({Order.status: "settling"}, synchronize_session=False)
    if changed != 1:
        raise BizError("订单状态已变化，请刷新后重试", status_code=409)
    db.expire(order)
    db.refresh(order)

    ssh_info = reveal(order.ssh_info)
    if not valid_ssh_info(ssh_info):
        raise BizError("SSH 连接信息无效，请联系交付人员重新填写", status_code=409)
    amount = Decimal(str(order.amount))
    wallet = db.query(Wallet).filter(
        Wallet.user_id == order.user_id,
    ).with_for_update().first()
    if wallet is None:
        raise BizError("钱包不存在", status_code=404)

    now = datetime.now(timezone.utc)
    capture_order_funding(order, wallet, db, captured_at=now)
    order.status = "completed"
    order.lifecycle_policy_version = "reserved-v1"
    order.last_modified_platform = _trusted_platform(platform)
    order.start_at = now
    order.end_at = (
        now + timedelta(hours=order.purchase_hours)
        if order.purchase_hours is not None
        else now + timedelta(days=order.cycle_days)
    )
    order.confirmed_at = now
    order.delivery_due_at = None
    order.confirmation_due_at = None
    order.dispute_due_at = None
    if original_status == "disputed":
        order.dispute_resolution = "release"
        order.dispute_resolution_note = resolution_note
        order.dispute_resolved_at = now
        order.dispute_resolved_by = resolved_by

    payment_entry = db.query(Ledger).filter(
        Ledger.ref_order_id == order.id,
        Ledger.type == "pay",
    ).first()
    if payment_entry is None:
        db.add(Ledger(
            user_id=order.user_id,
            wallet_id=wallet.id,
            type="pay",
            # The balance was already debited by the immutable freeze event.
            # Confirmation captures frozen funds without subtracting twice.
            direction="internal",
            amount=amount,
            balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=order.id,
            event_key=f"order_capture:{order.id}",
            remark=(
                f"购买{'持有' if order.purchase_type == 'holding' else '使用'}"
                f"·已确认交付({order.order_no})"
            ),
        ))

    # SSH delivery grants usage only; synthetic compute revenue stays disabled.
    quantity = max(int(order.quantity or 1), 1)
    unit_value = (amount / Decimal(quantity)).quantize(Decimal("0.0001"))
    asset = db.query(Asset).filter(Asset.order_id == order.id).first()
    if asset is None:
        asset = Asset(
            user_id=order.user_id,
            product_id=order.product_id,
            order_id=order.id,
            quantity=quantity,
            value=unit_value,
            daily_rate=Decimal("0"),
            status="active",
            start_at=now,
            end_at=order.end_at,
            purchase_type=order.purchase_type or "usage",
            rebate_status=None,
            rebate_amount=0,
        )
        db.add(asset)
        db.flush()

    # Commercial proceeds are withdrawable. All reward writers below remain
    # independent and only credit non-withdrawable in-app card-hours.
    settle_merchant_sale(order, db, settled_at=now)
    create_consumer_order_accrual(order, asset, now, db)
    create_supplier_order_accrual(order, now, db)
    from app.routers.invite import process_first_order_reward
    process_first_order_reward(order.user_id, order.id, db)
    process_invite_order_event(order, db, event_at=now)
    return True


def _refund_reserved_order(
    order: Order,
    db: Session,
    *,
    platform: str,
    reason: str,
    allowed_statuses: tuple[str, ...],
    resolved_by: int | None = None,
) -> bool:
    """Refund a reserved order exactly once and restore its inventory."""

    current_status = db.query(Order.status).filter(Order.id == order.id).scalar()
    if current_status == "canceled":
        return False
    original_status = str(current_status)
    changed = db.query(Order).filter(
        Order.id == order.id,
        Order.status.in_(allowed_statuses),
    ).update({Order.status: "refunding"}, synchronize_session=False)
    if changed != 1:
        raise BizError("订单状态已变化，请刷新后重试", status_code=409)
    db.expire(order)
    db.refresh(order)
    if db.query(Asset).filter(Asset.order_id == order.id).first() is not None:
        raise BizError("订单已生成资产，不能按未交付订单退款", status_code=409)

    refund = Decimal(str(order.amount))
    wallet = db.query(Wallet).filter(
        Wallet.user_id == order.user_id,
    ).with_for_update().first()
    if wallet is None:
        raise BizError("钱包不存在", status_code=404)
    now = datetime.now(timezone.utc)
    refund_order_funding(order, wallet, db, refunded_at=now)

    product = db.query(Product).filter(Product.id == order.product_id).with_for_update().first()
    if product:
        restored_stock = max(int(product.stock or 0), 0) + max(int(order.quantity or 1), 1)
        if product_market_source(product) == "kai" and product.platform_stock_cap is not None:
            restored_stock = min(restored_stock, max(int(product.platform_stock_cap), 0))
        product.stock = restored_stock

    order.status = "canceled"
    order.canceled_at = now
    order.stock_released_at = now
    order.last_modified_platform = _trusted_platform(platform)
    order.delivery_due_at = None
    order.confirmation_due_at = None
    order.dispute_due_at = None
    if original_status == "disputed":
        order.dispute_resolution = "refund"
        order.dispute_resolution_note = reason
        order.dispute_resolved_at = now
        order.dispute_resolved_by = resolved_by

    event_key = f"order_refund:{order.id}"
    if db.query(Ledger).filter(Ledger.event_key == event_key).first() is None:
        db.add(Ledger(
            user_id=order.user_id,
            wallet_id=wallet.id,
            type="refund",
            direction="in",
            amount=refund,
            balance_after=spendable_wallet_balance(wallet, db),
            ref_order_id=order.id,
            event_key=event_key,
            remark=f"订单退款 {order.order_no}: {reason}",
        ))
    return True


@router.post("/{oid}/confirm")
def confirm_delivery(
    oid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = db.query(Order).filter(
        Order.id == oid,
        Order.user_id == user.id,
    ).first()
    if not order:
        raise BizError("订单不存在", status_code=404)
    if order.status in ("completed", "running", "done"):
        return success(_order_out(order, db))
    if order.status != "delivering":
        raise BizError("当前订单状态不可确认", status_code=409)
    try:
        _complete_reserved_order(order, db, platform=_trusted_platform(platform))
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise BizError("确认交付失败，请重试")
    db.refresh(order)
    return success(_order_out(order, db))


@router.post("/{oid}/dispute")
def dispute_delivery(
    oid: int,
    data: OrderDisputeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = db.query(Order).filter(
        Order.id == oid,
        Order.user_id == user.id,
    ).first()
    if not order:
        raise BizError("订单不存在", status_code=404)
    reason = data.reason.strip()
    if order.status == "disputed" and order.dispute_reason == reason:
        return success(_order_out(order, db))
    if order.status != "delivering":
        raise BizError("仅待确认交付订单可以发起争议", status_code=409)
    now = datetime.now(timezone.utc)
    changed = db.query(Order).filter(
        Order.id == order.id,
        Order.status == "delivering",
        or_(Order.confirmation_due_at.is_(None), Order.confirmation_due_at > now),
    ).update({
        Order.status: "disputed",
        Order.disputed_at: now,
        Order.dispute_due_at: now + timedelta(
            hours=max(int(settings.ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS), 1)
        ),
        Order.dispute_reason: reason,
        Order.last_modified_platform: _trusted_platform(platform),
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("订单状态已变化，请刷新后重试", status_code=409)
    db.commit()
    db.expire_all()
    current = db.query(Order).filter(Order.id == order.id).populate_existing().first()
    return success(_order_out(current, db))


@router.post("/{oid}/dispute/resolve")
def resolve_delivery_dispute(
    oid: int,
    data: OrderDisputeResolveIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = db.query(Order).filter(Order.id == oid).populate_existing().first()
    if not order:
        raise BizError("订单不存在", status_code=404)
    if (
        data.action == "refund"
        and order.status == "canceled"
        and order.dispute_resolution == "refund"
    ) or (
        data.action == "release"
        and order.status in ("completed", "running", "done")
        and order.dispute_resolution == "release"
    ):
        return success(_order_out(order, db))
    if order.status != "disputed":
        raise BizError("该订单当前没有待处理争议", status_code=409)
    try:
        if data.action == "refund":
            _refund_reserved_order(
                order,
                db,
                platform=_trusted_platform(platform),
                reason=data.note.strip(),
                allowed_statuses=("disputed",),
                resolved_by=admin.id,
            )
        else:
            _complete_reserved_order(
                order,
                db,
                platform=_trusted_platform(platform),
                allowed_statuses=("disputed",),
                resolved_by=admin.id,
                resolution_note=data.note.strip(),
            )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise BizError("争议处理失败，请重试")
    db.expire_all()
    current = db.query(Order).filter(Order.id == oid).populate_existing().first()
    return success(_order_out(current, db))


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
    require_direct_trade_enabled()
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
            _begin_serialized_write_transaction(db)
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
            if product_market_source(p) == "wod" and o.purchase_hours is not None:
                raise BizError("商家算力续费需重新下单并完成交付验收", status_code=409)
            purchasable, unavailable_reason = product_purchase_availability(p, db)
            if not purchasable:
                raise BizError(unavailable_reason or "该资源暂不可在KAI星算内续费", status_code=409)
            _ensure_current_market_product(p, db)
            quantity = max(int(o.quantity or 1), 1)
            if o.purchase_hours is not None:
                if data.cycle_days is not None or not valid_purchase_hours(data.hours):
                    raise BizError("该订单仅支持按 1 至 720 的整数小时续费", status_code=422)
                renewal_hours = int(data.hours)
                renewal_days = None
                if product_market_source(p) == "kai":
                    unit_amount = _calc_kai_hour_amount(p, renewal_hours)
                    amount = _calc_kai_hour_amount(p, renewal_hours, quantity)
                else:
                    unit_amount = _calc_merchant_hour_amount(p, renewal_hours)
                    amount = _calc_merchant_hour_amount(p, renewal_hours, quantity)
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

            spend_renewal_funding(o, renewal, wallet, amount, db, captured_at=now)
            o.end_at = new_end
            o.amount = renewal.total_amount_after
            o.last_modified_platform = platform
            if renewal_hours is not None:
                o.purchase_hours = renewal.total_purchase_hours_after
            else:
                o.cycle_days = renewal.total_cycle_days_after
            o.status = "running"
            o.lifecycle_policy_version = "reserved-v1"
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
            settle_merchant_sale(o, db, renewal=renewal, settled_at=now)
            if asset:
                create_consumer_renewal_accrual(o, renewal, asset, now, db)
            create_supplier_renewal_accrual(o, renewal, now, db)
            process_invite_renewal_event(o, renewal, db, event_at=now)
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
    order = db.query(Order).filter(
        Order.id == oid, Order.user_id == user.id,
    ).first()
    if not order:
        raise BizError("订单不存在", status_code=404)
    if order.status == "canceled":
        return success(_order_out(order, db))
    if order.status != "paid":
        raise BizError("当前订单不可直接取消；已交付订单请发起争议", status_code=409)
    try:
        _refund_reserved_order(
            order,
            db,
            platform=_trusted_platform(platform),
            reason="买家在交付前取消",
            allowed_statuses=("paid",),
        )
        db.commit()
    except BizError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise BizError("取消失败，请重试")
    db.refresh(order)
    return success(_order_out(order, db))
