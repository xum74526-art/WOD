from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import math
import secrets
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Ledger
from app.models.payment import PaymentOrder
from app.models.wallet import Wallet
from app.services.notification_service import create_notification
from app.utils.response import BizError


PROVIDER = "qixiangpay"
SUCCESS_STATUS = "TRADE_SUCCESS"
SUPPORTED_PAYMENT_TYPES = frozenset({"alipay", "wxpay"})
PAYMENT_TIME_FIELDS = ("endtime",)
PAYMENT_ORDER_STATUSES = frozenset({
    "pending",
    "paid",
    "expired",
    "failed",
    "review",
    "late_paid_review",
    "canceled",
})
_CHECKOUT_CREATE_LOCK = threading.Lock()
CREATE_PENDING = "CREATE_PENDING"
CREATE_UNKNOWN = "CREATE_UNKNOWN"
CREATE_FAILED = "CREATE_FAILED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def canonicalize(params: dict) -> str:
    """Return the exact Qixiang Pay MD5 canonical string.

    The provider contract sorts non-empty fields by ASCII key, excludes
    ``sign`` and ``sign_type``, and signs raw values before form/query URL
    encoding.  Protocol field names are ASCII, so Python's normal string order
    is the required order here.
    """
    pairs: list[tuple[str, str]] = []
    for raw_key, raw_value in params.items():
        key = str(raw_key)
        if key in {"sign", "sign_type"} or raw_value is None:
            continue
        value = str(raw_value)
        if value == "":
            continue
        pairs.append((key, value))
    pairs.sort(key=lambda item: item[0])
    return "&".join(f"{key}={value}" for key, value in pairs)


def sign_params(params: dict) -> str:
    key = str(settings.QIXIANGPAY_KEY or "")
    if not key:
        raise BizError("七相支付商户密钥尚未配置", status_code=503)
    payload = (canonicalize(params) + key).encode("utf-8")
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def verify_params(params: dict) -> bool:
    if str(params.get("sign_type") or "").strip().upper() != "MD5":
        return False
    supplied = str(params.get("sign") or "")
    if len(supplied) != 32 or not settings.QIXIANGPAY_KEY:
        return False
    expected = sign_params(params)
    # Constant-time comparison prevents the callback endpoint from becoming a
    # byte-by-byte MD5 oracle.
    return hmac.compare_digest(expected, supplied)


def configured_payment_types() -> tuple[str, ...]:
    configured: list[str] = []
    seen: set[str] = set()
    for raw_value in str(settings.QIXIANGPAY_PAYMENT_TYPES or "").split(","):
        payment_type = raw_value.strip().lower()
        if payment_type in SUPPORTED_PAYMENT_TYPES and payment_type not in seen:
            configured.append(payment_type)
            seen.add(payment_type)
    return tuple(configured)


def checkout_ttl_seconds() -> int:
    # KAI's existing order contract is five minutes. The provider does not
    # expose an order-expiry or close API, so this is a local business deadline.
    return min(max(int(settings.QIXIANGPAY_CHECKOUT_TTL_SECONDS), 60), 300)


def _provider_http_timeout_seconds() -> float:
    try:
        timeout = float(settings.QIXIANGPAY_HTTP_TIMEOUT)
    except (TypeError, ValueError):
        timeout = 10.0
    if not math.isfinite(timeout):
        timeout = 10.0
    # Keep the actual network bound and the cross-worker fresh-claim window in
    # lockstep, so a second worker never recovers while the first can still be
    # waiting on the same create request.
    return min(max(timeout, 1.0), 55.0)


def _https_url_configured(value: str) -> bool:
    parsed = urlparse(str(value or ""))
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )


def provider_configured() -> bool:
    return bool(
        settings.PAYMENT_SERVICE_ENABLED
        and settings.QIXIANGPAY_ENABLED
        and str(settings.QIXIANGPAY_PID or "").strip()
        and str(settings.QIXIANGPAY_KEY or "")
        and _https_url_configured(settings.QIXIANGPAY_BASE_URL)
        and _https_url_configured(settings.QIXIANGPAY_NOTIFY_URL)
        and _https_url_configured(settings.QIXIANGPAY_RETURN_URL)
        and configured_payment_types()
    )


def public_config() -> dict:
    return {
        "provider": PROVIDER,
        "enabled": provider_configured(),
        "pid_configured": bool(str(settings.QIXIANGPAY_PID or "").strip()),
        "key_configured": bool(settings.QIXIANGPAY_KEY),
        "sign_version": "MD5",
        "card_hour_rmb_rate": float(settings.CARD_HOUR_RMB_RATE),
        "min_amount_cny": float(settings.QIXIANGPAY_MIN_AMOUNT_CNY),
        "max_amount_cny": float(settings.QIXIANGPAY_MAX_AMOUNT_CNY),
        "checkout_mode": "hosted_page",
        "checkout_ttl_seconds": checkout_ttl_seconds(),
        "payment_types": list(configured_payment_types()),
    }


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _payment_out(order: PaymentOrder, checkout_url: str | None = None) -> dict:
    now = utc_now()
    remaining = max(0, math.ceil((order.expires_at - now).total_seconds()))
    is_current_provider = order.provider == PROVIDER
    is_supported_provider = order.provider in {PROVIDER, "mapay"}
    can_cancel = (
        is_current_provider
        and order.credited_at is None
        and order.status in {"expired", "failed"}
    )
    return {
        "order_no": order.order_no,
        "provider": order.provider,
        "provider_trade_no": order.provider_trade_no,
        "channel": order.channel,
        "status": order.status,
        "amount_cny": float(order.amount_cny),
        "card_hours": float(order.card_hours),
        "card_hour_rmb_rate": float(order.card_hour_rate),
        "checkout_url": checkout_url,
        "created_at": _iso_utc(order.created_at),
        "expires_at": _iso_utc(order.expires_at),
        "server_time": _iso_utc(now),
        "remaining_seconds": remaining,
        "is_expired": remaining == 0 and order.credited_at is None,
        "can_pay": (
            is_current_provider
            and order.status == "pending"
            and remaining > 0
        ),
        "can_query": is_supported_provider and order.credited_at is None,
        "can_cancel": can_cancel,
        "provider_status": order.provider_status,
        "failure_reason": order.failure_reason,
        "paid_at": _iso_utc(order.paid_at),
        "credited_at": _iso_utc(order.credited_at),
        "updated_at": _iso_utc(order.updated_at),
    }


def _require_payment_type(payment_type: str | None) -> str:
    normalized = str(payment_type or "").strip().lower()
    if not normalized:
        raise BizError("请选择支付宝或微信支付", status_code=400)
    if normalized not in SUPPORTED_PAYMENT_TYPES:
        raise BizError("不支持的支付方式", status_code=400)
    if normalized not in configured_payment_types():
        raise BizError("该支付方式当前不可用", status_code=400)
    return normalized


def _order_channel(payment_type: str | None) -> str:
    normalized = str(payment_type or "").strip().lower()
    if normalized not in SUPPORTED_PAYMENT_TYPES:
        raise BizError("充值订单支付方式无效", status_code=409)
    return normalized


def _require_provider_order(order: PaymentOrder) -> None:
    if order.provider != PROVIDER:
        raise BizError(
            "历史充值订单不能通过七相支付网关查询或取消",
            status_code=409,
        )


def _expire_order_if_due(order: PaymentOrder, *, now: datetime | None = None) -> bool:
    current = now or utc_now()
    if (
        order.credited_at is None
        and order.status == "pending"
        and order.expires_at <= current
    ):
        order.status = "expired"
        order.failure_reason = "支付时限已结束；如已付款请查询支付平台状态"
        return True
    return False


def _persist_order_expiry(
    db: Session,
    order: PaymentOrder,
    *,
    now: datetime | None = None,
) -> bool:
    current = now or utc_now()
    changed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.status == "pending",
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.expires_at <= current,
    ).update(
        {
            PaymentOrder.status: "expired",
            PaymentOrder.failure_reason: "支付时限已结束；如已付款请查询支付平台状态",
        },
        synchronize_session=False,
    )
    if changed:
        db.commit()
        db.refresh(order)
    return bool(changed)


def expire_pending_payment_orders(db: Session, *, now: datetime | None = None) -> int:
    """Persist local expiry for every provider without querying a new gateway."""
    current = now or utc_now()
    count = db.query(PaymentOrder).filter(
        PaymentOrder.status == "pending",
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.expires_at <= current,
    ).update(
        {
            PaymentOrder.status: "expired",
            PaymentOrder.failure_reason: "支付时限已结束；如已付款请查询支付平台状态",
        },
        synchronize_session=False,
    )
    return int(count or 0)


def create_recharge_order(
    db: Session,
    user_id: int,
    amount_cny: Decimal,
    *,
    payment_type: str | None,
) -> dict:
    if not provider_configured():
        raise BizError("七相支付尚未完成配置", status_code=503)
    channel = _require_payment_type(payment_type)
    minimum = Decimal(str(settings.QIXIANGPAY_MIN_AMOUNT_CNY)).quantize(Decimal("0.01"))
    maximum = Decimal(str(settings.QIXIANGPAY_MAX_AMOUNT_CNY)).quantize(Decimal("0.01"))
    amount = Decimal(str(amount_cny)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < minimum or amount > maximum:
        raise BizError(f"充值金额须在 {minimum:.2f} 至 {maximum:.2f} 元之间")
    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE)).quantize(Decimal("0.000001"))
    if rate <= 0:
        raise BizError("卡时兑换率配置无效", status_code=503)

    token = secrets.token_urlsafe(32)
    order = PaymentOrder(
        order_no=f"KAIQ{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}",
        user_id=user_id,
        provider=PROVIDER,
        channel=channel,
        status="pending",
        amount_cny=amount,
        card_hours=(amount / rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        card_hour_rate=rate,
        checkout_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=utc_now() + timedelta(seconds=checkout_ttl_seconds()),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    checkout_path = f"/api/payments/qixiang/checkout/{token}"
    base = str(settings.QIXIANGPAY_PUBLIC_API_BASE_URL or "").rstrip("/")
    checkout_url = f"{base}/payments/qixiang/checkout/{token}" if base else checkout_path
    return _payment_out(order, checkout_url)


def get_owned_order(db: Session, user_id: int, order_no: str) -> PaymentOrder:
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
        PaymentOrder.user_id == user_id,
    ).first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    return order


def payment_status(db: Session, user_id: int, order_no: str) -> dict:
    order = get_owned_order(db, user_id, order_no)
    _persist_order_expiry(db, order)
    return _payment_out(order)


def list_owned_payment_orders(
    db: Session,
    user_id: int,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    order_no: str | None = None,
) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "cancelled":
        normalized_status = "canceled"
    if normalized_status and normalized_status not in PAYMENT_ORDER_STATUSES:
        raise BizError("充值订单状态无效", status_code=400)
    normalized_order_no = str(order_no or "").strip().upper()
    if len(normalized_order_no) > 40:
        raise BizError("充值订单号格式无效", status_code=400)

    now = utc_now()
    expired = db.query(PaymentOrder).filter(
        PaymentOrder.user_id == user_id,
        PaymentOrder.status == "pending",
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.expires_at <= now,
    ).update(
        {
            PaymentOrder.status: "expired",
            PaymentOrder.failure_reason: "支付时限已结束；如已付款请查询支付平台状态",
        },
        synchronize_session=False,
    )
    if expired:
        db.commit()

    query = db.query(PaymentOrder).filter(PaymentOrder.user_id == user_id)
    if normalized_status:
        query = query.filter(PaymentOrder.status == normalized_status)
    if normalized_order_no:
        query = query.filter(PaymentOrder.order_no == normalized_order_no)
    total = query.count()
    orders = query.order_by(
        PaymentOrder.created_at.desc(),
        PaymentOrder.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
        "items": [_payment_out(item) for item in orders],
    }


def _client_ip(value: str | None) -> str:
    candidate = str(value or "").strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "127.0.0.1"


def resolve_checkout_client_ip(
    peer_ip: str | None,
    *,
    x_real_ip: str | None = None,
    x_forwarded_for: str | None = None,
) -> str | None:
    """Resolve a checkout IP without trusting client-controlled headers.

    Forwarded headers are considered only when the immediate TCP peer belongs
    to an explicitly configured proxy network. Malformed headers fail closed
    to the peer address instead of partially accepting an attacker-built chain.
    """
    try:
        peer = ipaddress.ip_address(str(peer_ip or "").strip())
    except ValueError:
        return None

    trusted_networks = []
    for raw_network in str(settings.QIXIANGPAY_TRUSTED_PROXY_CIDRS or "").split(","):
        candidate = raw_network.strip()
        if not candidate:
            continue
        try:
            trusted_networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            # A bad deployment entry must reduce trust, never broaden it.
            continue

    def is_trusted(address) -> bool:
        return any(
            address.version == network.version and address in network
            for network in trusted_networks
        )

    if not is_trusted(peer):
        return str(peer)

    if x_real_ip is not None:
        real_value = str(x_real_ip).strip()
        if not real_value or "," in real_value:
            return str(peer)
        try:
            return str(ipaddress.ip_address(real_value))
        except ValueError:
            return str(peer)

    if x_forwarded_for is not None:
        forwarded_values = [part.strip() for part in str(x_forwarded_for).split(",")]
        if not forwarded_values or any(not part for part in forwarded_values):
            return str(peer)
        try:
            forwarded = [ipaddress.ip_address(part) for part in forwarded_values]
        except ValueError:
            return str(peer)
        # Walk toward the client and skip only explicitly trusted proxy hops.
        for address in reversed(forwarded):
            if not is_trusted(address):
                return str(address)
        return str(forwarded[0])

    return str(peer)


def _gateway_url(path: str) -> str:
    base = str(settings.QIXIANGPAY_BASE_URL or "").rstrip("/")
    if not _https_url_configured(base):
        raise BizError("七相支付网关地址配置无效", status_code=503)
    return f"{base}/{path.lstrip('/')}"


def _provider_json(response: httpx.Response, error_message: str) -> dict:
    limit = min(max(int(settings.QIXIANGPAY_MAX_RESPONSE_BYTES), 1024), 1024 * 1024)
    content = response.content
    if len(content) > limit:
        raise BizError(error_message, status_code=502)
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise BizError(error_message, status_code=502) from None
    if not isinstance(payload, dict):
        raise BizError(error_message, status_code=502)
    return payload


def _validated_checkout_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if not (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and len(url) <= 1024
    ):
        raise BizError("支付平台返回了无效收银台地址", status_code=502)
    return url


def _provider_trade_no(db: Session, order: PaymentOrder, params: dict) -> str:
    trade_no = str(params.get("trade_no") or "").strip()
    if not trade_no:
        raise BizError("支付平台响应缺少平台订单号", status_code=502)
    if order.provider_trade_no and order.provider_trade_no != trade_no:
        raise BizError("充值订单的平台订单号发生冲突")
    other = db.query(PaymentOrder).filter(
        PaymentOrder.provider_trade_no == trade_no,
        PaymentOrder.id != order.id,
    ).first()
    if other:
        raise BizError("平台订单号已被其他订单使用")
    return trade_no


def _mark_create_unknown(db: Session, order: PaymentOrder) -> None:
    changed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status == "pending",
        PaymentOrder.provider_checkout_url.is_(None),
    ).update(
        {
            PaymentOrder.provider_status: CREATE_UNKNOWN,
            PaymentOrder.failure_reason: (
                "支付平台下单结果尚未确认；为避免重复创建上游订单，"
                "本订单不会再次提交，请返回重新发起"
            ),
        },
        synchronize_session=False,
    )
    if changed:
        db.commit()
    else:
        db.rollback()


def _create_pending_is_fresh(order: PaymentOrder) -> bool:
    started_at = order.checkout_started_at
    if started_at is None:
        return False
    # Leave enough time for the configured HTTP request to complete, while
    # bounding a bad configuration so an abandoned order is not blocked for
    # longer than one minute before recovery is attempted.
    fresh_seconds = max(_provider_http_timeout_seconds() + 5.0, 10.0)
    return started_at > utc_now() - timedelta(seconds=fresh_seconds)


def _recover_uncertain_checkout(db: Session, order: PaymentOrder) -> str:
    """Query an uncertain create exactly once; never repeat the create POST."""
    try:
        payload = _query_provider_payload(db, order)
    except BizError:
        raise BizError(
            "支付平台下单结果仍待确认；本订单不会重复提交，请返回重新发起",
            status_code=409,
        ) from None

    if _provider_reports_success(payload):
        normalized = dict(payload)
        normalized["trade_status"] = SUCCESS_STATUS
        credit_verified_payment(db, order, normalized, observed_at=utc_now())
        db.refresh(order)
        if order.credited_at is not None:
            raise BizError("支付已经确认，请返回 KAI 查看余额", status_code=410)
        if order.status in {"review", "late_paid_review"}:
            raise BizError("支付结果正在人工复核，请返回 KAI 查看状态", status_code=409)
    trade_no = _provider_trade_no(db, order, payload)
    try:
        provider_status = int(payload.get("status"))
    except (TypeError, ValueError):
        provider_status = -1
    changed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status.in_(("pending", "expired", "failed")),
        PaymentOrder.provider_checkout_url.is_(None),
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update(
        {
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_status: str(provider_status),
            PaymentOrder.status: "failed",
            PaymentOrder.checkout_started_at: None,
            PaymentOrder.failure_reason: (
                "支付平台已存在该订单，但未返回可恢复的收银台地址；"
                "未重复创建，请重新发起充值"
            ),
        },
        synchronize_session=False,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("平台订单号已被其他订单使用", status_code=409) from exc
    if not changed:
        db.refresh(order)
        if order.credited_at is not None:
            raise BizError("支付已经确认，请返回 KAI 查看余额", status_code=410)
    raise BizError(
        "支付平台已存在该订单，当前收银台地址无法恢复，请重新发起充值",
        status_code=409,
    )


def checkout_redirect_url(db: Session, token: str, *, client_ip: str | None) -> str:
    """Create at most one upstream order per local checkout token."""
    # SQLite ignores SELECT FOR UPDATE in local/test deployments. The process
    # lock closes that gap; PostgreSQL's row lock below additionally protects
    # production deployments with multiple worker processes.
    with _CHECKOUT_CREATE_LOCK:
        return _checkout_redirect_url_locked(db, token, client_ip=client_ip)


def _checkout_redirect_url_locked(db: Session, token: str, *, client_ip: str | None) -> str:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    # PostgreSQL holds this row lock through the provider request. The stored
    # URL and unique provider trade number make later reopens read-only.
    order = db.query(PaymentOrder).filter(
        PaymentOrder.checkout_token_hash == token_hash,
    ).populate_existing().with_for_update().first()
    if not order:
        raise BizError("支付链接无效", status_code=404)
    _require_provider_order(order)
    if order.credited_at:
        raise BizError("支付已经确认，请返回 KAI 查看余额", status_code=410)
    if order.expires_at <= utc_now():
        _persist_order_expiry(db, order)
        raise BizError("支付链接已过期，请返回 KAI 重新发起", status_code=410)
    if order.status != "pending":
        raise BizError("该充值订单已停止支付，请返回 KAI 查询状态", status_code=410)
    if order.provider_checkout_url:
        return _validated_checkout_url(order.provider_checkout_url)
    if order.provider_status == CREATE_PENDING and _create_pending_is_fresh(order):
        raise BizError("支付订单正在创建，请稍后重试", status_code=409)
    if order.provider_status in {CREATE_PENDING, CREATE_UNKNOWN, "0"}:
        return _recover_uncertain_checkout(db, order)
    if not provider_configured():
        raise BizError("支付服务暂不可用", status_code=503)

    fields = {
        "pid": str(settings.QIXIANGPAY_PID).strip(),
        "type": _require_payment_type(order.channel),
        "out_trade_no": order.order_no,
        "notify_url": settings.QIXIANGPAY_NOTIFY_URL,
        "return_url": settings.QIXIANGPAY_RETURN_URL,
        "name": "KAI钱包卡时充值",
        "money": f"{order.amount_cny:.2f}",
        "clientip": _client_ip(client_ip),
        "device": "jump",
        "param": order.order_no,
        "sign_type": "MD5",
    }
    fields["sign"] = sign_params(fields)
    # Persist the outbound intent before network I/O. If the process loses the
    # response after the provider created the order, later opens query by the
    # same out_trade_no and never issue another create POST.
    order.provider_status = CREATE_PENDING
    order.checkout_started_at = utc_now()
    order.failure_reason = None
    db.commit()
    try:
        response = httpx.post(
            _gateway_url("mapi.php"),
            data=fields,
            headers={"Accept": "application/json"},
            timeout=_provider_http_timeout_seconds(),
        )
        response.raise_for_status()
    except httpx.HTTPError:
        _mark_create_unknown(db, order)
        # Do not chain the HTTP exception: its request representation can carry
        # form fields and must never leak the merchant key/signature to logs.
        raise BizError("支付平台下单失败，请稍后重试", status_code=502) from None
    try:
        payload = _provider_json(response, "支付平台下单失败，请稍后重试")
    except BizError:
        _mark_create_unknown(db, order)
        raise
    if str(payload.get("code")) != "1":
        db.query(PaymentOrder).filter(
            PaymentOrder.id == order.id,
            PaymentOrder.credited_at.is_(None),
            PaymentOrder.status == "pending",
        ).update(
            {
                PaymentOrder.provider_status: CREATE_FAILED,
                PaymentOrder.status: "failed",
                PaymentOrder.checkout_started_at: None,
                PaymentOrder.failure_reason: "支付平台明确拒绝创建该订单，请重新发起",
            },
            synchronize_session=False,
        )
        db.commit()
        raise BizError("支付平台下单失败，请稍后重试", status_code=502)

    try:
        trade_no = _provider_trade_no(db, order, payload)
        payurl = _validated_checkout_url(payload.get("payurl"))
    except BizError:
        # code=1 means the provider may already own this out_trade_no. Keep the
        # local order in recover-only mode even when its response is unusable.
        _mark_create_unknown(db, order)
        raise
    changed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status == "pending",
        PaymentOrder.provider_checkout_url.is_(None),
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update(
        {
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_checkout_url: payurl,
            PaymentOrder.provider_status: "0",
            PaymentOrder.checkout_started_at: None,
            PaymentOrder.failure_reason: None,
        },
        synchronize_session=False,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
        if (
            current
            and current.provider_trade_no == trade_no
            and current.provider_checkout_url
        ):
            return _validated_checkout_url(current.provider_checkout_url)
        raise BizError("平台订单号已被其他订单使用", status_code=409) from exc
    if not changed:
        current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
        if current and current.provider_checkout_url:
            return _validated_checkout_url(current.provider_checkout_url)
        if current and current.credited_at is not None:
            raise BizError("支付已经确认，请返回 KAI 查看余额", status_code=410)
        raise BizError("充值订单状态已变化，请重新查询", status_code=409)
    db.refresh(order)
    return payurl


def _validate_provider_payment(order: PaymentOrder, params: dict) -> None:
    _require_provider_order(order)
    if str(params.get("pid") or "") != str(settings.QIXIANGPAY_PID).strip():
        raise BizError("支付通知商户号不匹配")
    if str(params.get("out_trade_no") or "") != order.order_no:
        raise BizError("支付通知订单号不匹配")
    if str(params.get("type") or "").strip().lower() != _order_channel(order.channel):
        raise BizError("支付通知渠道不匹配")
    try:
        notified_money = Decimal(str(params.get("money"))).quantize(Decimal("0.01"))
    except Exception as exc:
        raise BizError("支付通知金额无效") from exc
    if notified_money != Decimal(order.amount_cny).quantize(Decimal("0.01")):
        raise BizError("支付通知金额不匹配")
    if params.get("param") not in (None, "", order.order_no):
        raise BizError("支付通知业务参数不匹配")


def _parse_provider_time(value: object) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    parsed: datetime | None = None
    iso_value = text_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        for time_format in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text_value, time_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        try:
            provider_zone = ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE)
        except ZoneInfoNotFoundError:
            return None
        parsed = parsed.replace(tzinfo=provider_zone)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _provider_paid_at(params: dict) -> tuple[datetime | None, bool]:
    for field in PAYMENT_TIME_FIELDS:
        if field in params and str(params.get(field) or "").strip():
            return _parse_provider_time(params[field]), True
    return None, False


def _payment_deadline_decision(
    order: PaymentOrder,
    params: dict,
    *,
    observed_at: datetime,
) -> tuple[str, datetime | None, str | None]:
    provider_paid_at, time_was_supplied = _provider_paid_at(params)
    if time_was_supplied and provider_paid_at is None:
        return (
            "review",
            None,
            "支付平台已报告成功，但支付完成时间无法解析，未自动入账",
        )
    if provider_paid_at is not None:
        if provider_paid_at <= order.expires_at:
            return "credit", provider_paid_at, None
        return (
            "late_paid_review",
            provider_paid_at,
            "支付完成时间晚于订单截止时间，未自动入账，等待人工复核",
        )
    if observed_at <= order.expires_at:
        return "credit", observed_at, None
    return (
        "review",
        None,
        "订单截止后才确认支付成功，且平台未提供支付完成时间，未自动入账",
    )


def _record_success_for_review(
    db: Session,
    order: PaymentOrder,
    params: dict,
    *,
    status: str,
    reason: str,
    provider_paid_at: datetime | None,
) -> bool:
    _validate_provider_payment(order, params)
    trade_no = _provider_trade_no(db, order, params)
    if order.credited_at is not None:
        return False
    updates = {
        PaymentOrder.provider_trade_no: trade_no,
        PaymentOrder.provider_status: SUCCESS_STATUS,
        PaymentOrder.status: status,
        PaymentOrder.checkout_started_at: None,
        PaymentOrder.failure_reason: reason[:160],
    }
    if provider_paid_at is not None:
        updates[PaymentOrder.paid_at] = provider_paid_at
    claimed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update(updates, synchronize_session=False)
    if claimed == 0:
        db.rollback()
        return False
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("平台订单号已被其他订单使用") from exc
    return False


def credit_verified_payment(
    db: Session,
    order: PaymentOrder,
    params: dict,
    *,
    observed_at: datetime | None = None,
) -> bool:
    """Credit a verified callback/query success at most once."""
    _validate_provider_payment(order, params)
    trade_no = _provider_trade_no(db, order, params)
    if order.credited_at is not None:
        return False

    now = observed_at or utc_now()
    decision, paid_at, reason = _payment_deadline_decision(order, params, observed_at=now)
    if decision != "credit":
        return _record_success_for_review(
            db,
            order,
            params,
            status=decision,
            reason=reason or "支付成功待人工复核",
            provider_paid_at=paid_at,
        )

    user_id = order.user_id
    payment_order_id = order.id
    amount_cny = Decimal(order.amount_cny).quantize(Decimal("0.01"))
    card_hours = Decimal(order.card_hours).quantize(Decimal("0.000001"))
    claimed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status != "canceled",
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update(
        {
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_status: SUCCESS_STATUS,
            PaymentOrder.status: "paid",
            PaymentOrder.checkout_started_at: None,
            PaymentOrder.failure_reason: None,
            PaymentOrder.paid_at: paid_at or now,
            PaymentOrder.credited_at: now,
        },
        synchronize_session=False,
    )
    if claimed == 0:
        db.rollback()
        current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
        if current and current.status == "canceled" and current.credited_at is None:
            return _record_success_for_review(
                db,
                current,
                params,
                status="review",
                reason="已取消的充值订单随后收到支付成功，未自动入账，等待人工复核",
                provider_paid_at=paid_at,
            )
        return False

    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).with_for_update().first()
    if not wallet:
        db.rollback()
        raise BizError("钱包不存在", status_code=404)
    wallet.balance = (Decimal(wallet.balance) + card_hours).quantize(Decimal("0.000001"))
    db.add(Ledger(
        user_id=user_id,
        wallet_id=wallet.id,
        type="recharge",
        direction="in",
        amount=card_hours,
        balance_after=wallet.balance,
        ref_payment_order_id=payment_order_id,
        remark=f"七相支付人民币 {amount_cny:.2f} 元兑换 {card_hours} 卡时",
    ))
    create_notification(
        db,
        user_id=user_id,
        title="钱包充值到账",
        content=f"人民币 {amount_cny:.2f} 元支付成功，已兑换 {card_hours} 卡时。",
        title_en="Wallet recharge received",
        content_en=f"CNY {amount_cny:.2f} was paid and converted to {card_hours} CH.",
        notification_type="wallet",
        action_url="/pages/wallet/index",
        dedupe_key=f"payment:{payment_order_id}:credited",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.query(PaymentOrder).filter(PaymentOrder.id == payment_order_id).first()
        if existing and existing.credited_at is not None:
            return False
        raise BizError("充值入账幂等校验失败，请人工复核", status_code=409) from exc
    return True


def _provider_query_configured() -> bool:
    return bool(
        settings.PAYMENT_SERVICE_ENABLED
        and settings.QIXIANGPAY_ENABLED
        and str(settings.QIXIANGPAY_PID or "").strip()
        and str(settings.QIXIANGPAY_KEY or "")
        and _https_url_configured(settings.QIXIANGPAY_BASE_URL)
    )


def _query_provider_payload(db: Session, order: PaymentOrder) -> dict:
    _require_provider_order(order)
    if not _provider_query_configured():
        raise BizError("七相支付尚未完成配置", status_code=503)
    params = {
        "act": "order",
        "pid": str(settings.QIXIANGPAY_PID).strip(),
        "key": settings.QIXIANGPAY_KEY,
        "out_trade_no": order.order_no,
    }
    try:
        response = httpx.get(
            _gateway_url("api.php"),
            params=params,
            headers={"Accept": "application/json"},
            timeout=_provider_http_timeout_seconds(),
        )
        response.raise_for_status()
    except httpx.HTTPError:
        # The official query contract carries KEY in the query string. Never
        # chain/log the request exception because its URL contains that secret.
        raise BizError("支付平台订单查询失败，请稍后重试", status_code=502) from None
    payload = _provider_json(response, "支付平台订单查询失败，请稍后重试")
    if str(payload.get("code")) != "1":
        raise BizError("支付平台暂未确认该订单", status_code=409)
    if str(payload.get("out_trade_no") or "") != order.order_no:
        raise BizError("支付平台查询订单号不匹配", status_code=502)
    _validate_provider_payment(order, payload)
    _provider_trade_no(db, order, payload)
    try:
        provider_status = int(payload.get("status"))
    except (TypeError, ValueError):
        raise BizError("支付平台返回了未知订单状态", status_code=502) from None
    if provider_status not in {0, 1}:
        raise BizError("支付平台返回了未知订单状态", status_code=502)
    return payload


def _provider_reports_success(payload: dict) -> bool:
    try:
        return int(payload.get("status")) == 1
    except (TypeError, ValueError):
        return False


def handle_notification(db: Session, params: dict) -> bool:
    if not verify_params(params):
        raise BizError("支付通知签名无效")
    order_no = str(params.get("out_trade_no") or "")
    order = db.query(PaymentOrder).filter(PaymentOrder.order_no == order_no).first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    _require_provider_order(order)
    status = str(params.get("trade_status") or "")
    if status != SUCCESS_STATUS:
        _validate_provider_payment(order, params)
        trade_no = _provider_trade_no(db, order, params)
        updates = {
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_status: status[:64],
        }
        if order.expires_at <= utc_now():
            updates.update({
                PaymentOrder.status: "expired",
                PaymentOrder.failure_reason: (
                    "支付时限已结束；如已付款请查询支付平台状态"
                ),
            })
        changed = db.query(PaymentOrder).filter(
            PaymentOrder.id == order.id,
            PaymentOrder.credited_at.is_(None),
            PaymentOrder.status.in_(("pending", "expired", "failed")),
            or_(
                PaymentOrder.provider_trade_no.is_(None),
                PaymentOrder.provider_trade_no == trade_no,
            ),
        ).update(updates, synchronize_session=False)
        if changed:
            db.commit()
        else:
            db.rollback()
            db.query(PaymentOrder).filter(
                PaymentOrder.id == order.id,
            ).populate_existing().first()
        return False

    received_at = utc_now()
    provider_paid_at, time_was_supplied = _provider_paid_at(params)
    if received_at > order.expires_at and (not time_was_supplied or provider_paid_at is None):
        try:
            queried = _query_provider_payload(db, order)
        except BizError:
            credit_verified_payment(db, order, params, observed_at=received_at)
            return True
        if _provider_reports_success(queried):
            normalized = dict(queried)
            normalized["trade_status"] = SUCCESS_STATUS
            credit_verified_payment(db, order, normalized, observed_at=received_at)
            return True
        _record_success_for_review(
            db,
            order,
            params,
            status="review",
            reason="支付回调报告成功，但订单查询尚未确认，未自动入账",
            provider_paid_at=None,
        )
        return True

    credit_verified_payment(db, order, params, observed_at=received_at)
    return True


def query_provider_and_reconcile(db: Session, order: PaymentOrder) -> dict:
    _require_provider_order(order)
    if order.credited_at is not None:
        return _payment_out(order)
    _persist_order_expiry(db, order)
    payload = _query_provider_payload(db, order)
    if _provider_reports_success(payload):
        normalized = dict(payload)
        normalized["trade_status"] = SUCCESS_STATUS
        credit_verified_payment(db, order, normalized, observed_at=utc_now())
    else:
        try:
            provider_status = int(payload.get("status"))
        except (TypeError, ValueError):
            raise BizError("支付平台返回了未知订单状态", status_code=502) from None
        if provider_status != 0:
            raise BizError("支付平台返回了未知订单状态", status_code=502)
        trade_no = _provider_trade_no(db, order, payload)
        updates = {
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_status: "0",
        }
        if order.expires_at <= utc_now():
            updates.update({
                PaymentOrder.status: "expired",
                PaymentOrder.failure_reason: (
                    "支付时限已结束；如已付款请查询支付平台状态"
                ),
            })
        changed = db.query(PaymentOrder).filter(
            PaymentOrder.id == order.id,
            PaymentOrder.credited_at.is_(None),
            PaymentOrder.status.in_(("pending", "expired", "failed")),
            or_(
                PaymentOrder.provider_trade_no.is_(None),
                PaymentOrder.provider_trade_no == trade_no,
            ),
        ).update(updates, synchronize_session=False)
        if changed:
            db.commit()
        else:
            db.rollback()
    current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).populate_existing().first()
    if not current:
        raise BizError("充值订单不存在", status_code=404)
    return _payment_out(current)


def cancel_recharge_order(db: Session, order: PaymentOrder) -> dict:
    """Locally cancel an expired order after a fresh provider unpaid query."""
    _require_provider_order(order)
    if order.status == "canceled" and order.credited_at is None:
        return _payment_out(order)
    if order.credited_at is not None or order.status == "paid":
        raise BizError("充值订单已经支付到账，不能取消", status_code=409)
    if order.status in {"review", "late_paid_review"}:
        raise BizError("支付结果正在人工复核，不能取消", status_code=409)

    now = utc_now()
    has_provider_artifact = bool(
        order.provider_trade_no
        or order.provider_checkout_url
        or order.checkout_started_at
    )
    can_cancel_without_provider_query = not has_provider_artifact and (
        order.provider_status == CREATE_FAILED
        or (
            order.provider_status in (None, "")
            and order.expires_at <= now
        )
    )
    if can_cancel_without_provider_query:
        local_cancel = db.query(PaymentOrder).filter(
            PaymentOrder.id == order.id,
            PaymentOrder.credited_at.is_(None),
            PaymentOrder.status.in_(("pending", "expired", "failed")),
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_checkout_url.is_(None),
            PaymentOrder.checkout_started_at.is_(None),
        )
        if order.provider_status == CREATE_FAILED:
            local_cancel = local_cancel.filter(
                PaymentOrder.provider_status == CREATE_FAILED,
            )
        else:
            local_cancel = local_cancel.filter(
                or_(
                    PaymentOrder.provider_status.is_(None),
                    PaymentOrder.provider_status == "",
                ),
                PaymentOrder.expires_at <= now,
            )
        changed = local_cancel.update(
            {
                PaymentOrder.status: "canceled",
                PaymentOrder.failure_reason: (
                    "本地充值订单已取消；未向七相支付创建上游订单"
                ),
            },
            synchronize_session=False,
        )
        if changed:
            db.commit()
            db.refresh(order)
            return _payment_out(order)
        db.rollback()
        order = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
        if not order:
            raise BizError("充值订单不存在", status_code=404)
        if order.status == "canceled" and order.credited_at is None:
            return _payment_out(order)
        if order.credited_at is not None or order.status == "paid":
            raise BizError("充值订单已经支付到账，不能取消", status_code=409)
        if order.status in {"review", "late_paid_review"}:
            raise BizError("支付结果正在人工复核，不能取消", status_code=409)

    payload = _query_provider_payload(db, order)
    if _provider_reports_success(payload):
        normalized = dict(payload)
        normalized["trade_status"] = SUCCESS_STATUS
        credit_verified_payment(db, order, normalized, observed_at=now)
        db.refresh(order)
        raise BizError("支付平台已确认支付，不能取消充值订单", status_code=409)
    try:
        provider_status = int(payload.get("status"))
    except (TypeError, ValueError):
        raise BizError("支付平台返回了未知订单状态，未执行取消", status_code=502) from None
    if provider_status != 0:
        raise BizError("支付平台返回了未知订单状态，未执行取消", status_code=502)
    trade_no = _provider_trade_no(db, order, payload)
    if order.expires_at > now:
        changed = db.query(PaymentOrder).filter(
            PaymentOrder.id == order.id,
            PaymentOrder.credited_at.is_(None),
            PaymentOrder.status.in_(("pending", "expired", "failed")),
            PaymentOrder.expires_at > now,
            or_(
                PaymentOrder.provider_trade_no.is_(None),
                PaymentOrder.provider_trade_no == trade_no,
            ),
        ).update(
            {
                PaymentOrder.provider_trade_no: trade_no,
                PaymentOrder.provider_status: "0",
            },
            synchronize_session=False,
        )
        if changed:
            db.commit()
        else:
            db.rollback()
            current = db.query(PaymentOrder).filter(
                PaymentOrder.id == order.id,
            ).populate_existing().first()
            if current and (current.credited_at is not None or current.status == "paid"):
                raise BizError("充值订单已经支付到账，不能取消", status_code=409)
            if current and current.status in {"review", "late_paid_review"}:
                raise BizError("支付结果正在人工复核，不能取消", status_code=409)
            if current and current.status == "canceled":
                return _payment_out(current)
            raise BizError("充值订单状态已变化，请重新查询", status_code=409)
        raise BizError(
            "七相支付未提供商户主动关闭接口；支付时限内不能安全取消，请在倒计时结束后重试",
            status_code=409,
        )

    changed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status.in_(("pending", "expired", "failed")),
        PaymentOrder.expires_at <= now,
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update(
        {
            PaymentOrder.status: "canceled",
            PaymentOrder.provider_trade_no: trade_no,
            PaymentOrder.provider_status: "0",
            PaymentOrder.failure_reason: (
                "用户在支付时限结束后取消；七相支付查询确认未支付。"
                "平台未提供商户主动关闭接口"
            ),
        },
        synchronize_session=False,
    )
    if changed:
        db.commit()
        db.refresh(order)
        return _payment_out(order)

    db.rollback()
    current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
    if current and current.status == "canceled" and current.credited_at is None:
        return _payment_out(current)
    if current and current.credited_at is not None:
        raise BizError("充值订单已经支付到账，不能取消", status_code=409)
    if current and current.status in {"review", "late_paid_review"}:
        raise BizError("支付结果正在人工复核，不能取消", status_code=409)
    raise BizError("充值订单状态已变化，请重新查询", status_code=409)
