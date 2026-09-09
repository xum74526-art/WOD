from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Ledger
from app.models.payment import PaymentOrder
from app.models.wallet import Wallet
from app.services.notification_service import create_notification
from app.utils.response import BizError
from app.services.auth_session import normalize_platform


PROVIDER = "mapay"
SUCCESS_STATUS = "TRADE_SUCCESS"
SUPPORTED_PAYMENT_TYPES = frozenset({"alipay", "wxpay"})
FINAL_PROVIDER_FAILURES = frozenset({"TRADE_CLOSED", "TRADE_FAILED", "PAYERROR"})
PAYMENT_TIME_FIELDS = ("endtime", "pay_time", "paid_at")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _read_key(path_value: str, label: str) -> bytes:
    path = Path(path_value).expanduser()
    if not path_value or not path.is_file():
        raise BizError(f"{label}尚未配置", status_code=503)
    data = path.read_bytes()
    if not data or len(data) > 64 * 1024:
        raise BizError(f"{label}格式无效", status_code=503)
    return data.strip()


def _as_pem(data: bytes, kind: str) -> bytes:
    if b"-----BEGIN" in data:
        return data
    compact = b"".join(data.split())
    lines = [compact[index:index + 64] for index in range(0, len(compact), 64)]
    return (
        f"-----BEGIN {kind}-----\n".encode()
        + b"\n".join(lines)
        + f"\n-----END {kind}-----\n".encode()
    )


def canonicalize(params: dict, *, exclude_fields: set[str] | None = None) -> str:
    """MaPay V2 canonical string (values are intentionally not URL encoded)."""
    excluded = {"sign", "sign_type"}
    if exclude_fields:
        excluded.update(exclude_fields)
    pairs: list[tuple[str, str]] = []
    for raw_key, raw_value in params.items():
        key = str(raw_key)
        if key in excluded or raw_value is None:
            continue
        value = str(raw_value)
        if value == "":
            continue
        pairs.append((key, value))
    pairs.sort(key=lambda item: item[0])
    return "&".join(f"{key}={value}" for key, value in pairs)


def sign_params(params: dict) -> str:
    private_data = _as_pem(
        _read_key(settings.MAPAY_MERCHANT_PRIVATE_KEY_PATH, "码支付商户私钥"),
        "PRIVATE KEY",
    )
    try:
        private_key = serialization.load_pem_private_key(private_data, password=None)
        signature = private_key.sign(
            canonicalize(params).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (TypeError, ValueError) as exc:
        raise BizError("码支付商户私钥格式无效", status_code=503) from exc
    return base64.b64encode(signature).decode("ascii")


def verify_params(params: dict, *, exclude_fields: set[str] | None = None) -> bool:
    signature_text = str(params.get("sign") or "")
    if not signature_text:
        return False
    public_data = _as_pem(
        _read_key(settings.MAPAY_PLATFORM_PUBLIC_KEY_PATH, "码支付平台公钥"),
        "PUBLIC KEY",
    )
    try:
        public_key = serialization.load_pem_public_key(public_data)
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(
            signature,
            canonicalize(params, exclude_fields=exclude_fields).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, TypeError, ValueError):
        return False


def _verify_query_response(params: dict) -> bool:
    """Verify a direct TLS query response, including MaPay's observed legacy subset.

    MaPay's V2 query endpoint currently signs the business fields but omits the
    transport ``code`` and numeric ``status`` fields.  Public notifications do
    not use this compatibility path and remain strict full-field verification.
    """
    return verify_params(params) or verify_params(
        params,
        exclude_fields={"code", "status"},
    )


def configured_payment_types() -> tuple[str, ...]:
    configured: list[str] = []
    seen: set[str] = set()
    for raw_value in str(settings.MAPAY_PAYMENT_TYPES or "").split(","):
        payment_type = raw_value.strip().lower()
        if payment_type in SUPPORTED_PAYMENT_TYPES and payment_type not in seen:
            configured.append(payment_type)
            seen.add(payment_type)
    return tuple(configured)


def checkout_ttl_seconds() -> int:
    # The hosted cashier currently closes orders at five minutes. Never issue
    # a ZTW deadline that outlives the provider order even if a legacy server
    # still carries the former 1800-second environment value.
    return min(max(int(settings.MAPAY_CHECKOUT_TTL_SECONDS), 60), 300)


def provider_configured() -> bool:
    return bool(
        settings.PAYMENT_SERVICE_ENABLED
        and settings.MAPAY_ENABLED
        and settings.MAPAY_PID.strip()
        and settings.MAPAY_NOTIFY_URL.startswith("https://")
        and configured_payment_types()
        and Path(settings.MAPAY_MERCHANT_PRIVATE_KEY_PATH).expanduser().is_file()
        and Path(settings.MAPAY_PLATFORM_PUBLIC_KEY_PATH).expanduser().is_file()
    )


def public_config() -> dict:
    return {
        "provider": PROVIDER,
        "enabled": provider_configured(),
        "pid_configured": bool(settings.MAPAY_PID.strip()),
        "sign_version": "RSA-SHA256",
        "card_hour_rmb_rate": float(settings.CARD_HOUR_RMB_RATE),
        "min_amount_cny": float(settings.MAPAY_MIN_AMOUNT_CNY),
        "max_amount_cny": float(settings.MAPAY_MAX_AMOUNT_CNY),
        "checkout_mode": "hosted_page",
        "checkout_ttl_seconds": checkout_ttl_seconds(),
        "payment_types": list(configured_payment_types()),
    }


def _payment_out(order: PaymentOrder, checkout_url: str | None = None) -> dict:
    now = utc_now()
    remaining = max(0, math.ceil((order.expires_at - now).total_seconds()))
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
        "can_pay": order.status == "pending" and remaining > 0,
        "can_query": order.credited_at is None,
        "provider_status": order.provider_status,
        "failure_reason": order.failure_reason,
        "paid_at": _iso_utc(order.paid_at),
        "credited_at": _iso_utc(order.credited_at),
    }


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


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
    """Validate an existing order without depending on today's channel switch.

    A channel can be disabled for new checkouts while an already-created order
    still needs to accept and reconcile an authentic provider result.
    """
    normalized = str(payment_type or "").strip().lower()
    if not normalized:
        raise BizError("充值订单缺少支付方式", status_code=409)
    if normalized not in SUPPORTED_PAYMENT_TYPES:
        raise BizError("充值订单支付方式无效", status_code=409)
    return normalized


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
            PaymentOrder.last_modified_platform: "system",
        },
        synchronize_session=False,
    )
    if changed:
        db.commit()
        db.refresh(order)
    return bool(changed)


def expire_pending_payment_orders(db: Session, *, now: datetime | None = None) -> int:
    """Persist local checkout expiry; provider reconciliation remains available."""
    current = now or utc_now()
    count = db.query(PaymentOrder).filter(
        PaymentOrder.status == "pending",
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.expires_at <= current,
    ).update(
        {
            PaymentOrder.status: "expired",
            PaymentOrder.failure_reason: "支付时限已结束；如已付款请查询支付平台状态",
            PaymentOrder.last_modified_platform: "system",
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
    created_platform: str = "legacy",
) -> dict:
    if not provider_configured():
        raise BizError("码支付V2尚未完成密钥配置", status_code=503)
    channel = _require_payment_type(payment_type)
    minimum = Decimal(str(settings.MAPAY_MIN_AMOUNT_CNY)).quantize(Decimal("0.01"))
    maximum = Decimal(str(settings.MAPAY_MAX_AMOUNT_CNY)).quantize(Decimal("0.01"))
    amount = Decimal(str(amount_cny)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < minimum or amount > maximum:
        raise BizError(f"充值金额须在 {minimum:.2f} 至 {maximum:.2f} 元之间")
    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE)).quantize(Decimal("0.000001"))
    if rate <= 0:
        raise BizError("卡时兑换率配置无效", status_code=503)

    token = secrets.token_urlsafe(32)
    platform = normalize_platform(created_platform)
    order = PaymentOrder(
        order_no=f"WODR{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}",
        user_id=user_id,
        provider=PROVIDER,
        channel=channel,
        status="pending",
        amount_cny=amount,
        card_hours=(amount / rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        card_hour_rate=rate,
        checkout_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        created_platform=platform,
        last_modified_platform=platform,
        expires_at=utc_now() + timedelta(
            seconds=checkout_ttl_seconds()
        ),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    checkout_path = f"/api/payments/mapay/checkout/{token}"
    base = settings.MAPAY_PUBLIC_API_BASE_URL.rstrip("/")
    checkout_url = f"{base}/payments/mapay/checkout/{token}" if base else checkout_path
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


def checkout_html(db: Session, token: str) -> str:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    order = db.query(PaymentOrder).filter(PaymentOrder.checkout_token_hash == token_hash).first()
    if not order:
        raise BizError("支付链接无效", status_code=404)
    if order.credited_at:
        return "<!doctype html><meta charset='utf-8'><title>ZTW</title><p>支付已确认，可返回 ZTW 查看余额。</p>"
    if order.expires_at <= utc_now():
        _persist_order_expiry(db, order)
        raise BizError("支付链接已过期，请返回 ZTW 重新发起", status_code=410)
    if order.status != "pending":
        raise BizError("该充值订单已停止支付，请返回 ZTW 查询状态", status_code=410)
    if not provider_configured():
        raise BizError("支付服务暂不可用", status_code=503)
    channel = _require_payment_type(order.channel)

    fields = {
        "pid": settings.MAPAY_PID,
        "type": channel,
        "out_trade_no": order.order_no,
        "notify_url": settings.MAPAY_NOTIFY_URL,
        "name": "ZTW钱包卡时充值",
        "money": f"{order.amount_cny:.2f}",
        "param": order.order_no,
        "device": "mobile",
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "sign_type": "RSA",
    }
    fields["sign"] = sign_params(fields)
    action = settings.MAPAY_BASE_URL.rstrip("/") + "/api/pay/submit"
    hidden = "".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(str(value), quote=True)}">'
        for key, value in fields.items()
    )
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='referrer' content='no-referrer'><title>正在打开收银台</title>"
        "<style>body{font-family:system-ui;margin:0;display:grid;place-items:center;min-height:100vh}"
        "p{color:#59666b}</style></head><body><form id='pay' method='post' action='"
        + html.escape(action, quote=True)
        + "'>" + hidden + "<p>正在安全跳转到支付收银台…</p>"
        "<noscript><button type='submit'>继续支付</button></noscript></form>"
        "<script>document.getElementById('pay').submit()</script></body></html>"
    )


def _validate_provider_payment(order: PaymentOrder, params: dict) -> None:
    if str(params.get("pid") or "") != settings.MAPAY_PID:
        raise BizError("支付通知商户号不匹配")
    if str(params.get("out_trade_no") or "") != order.order_no:
        raise BizError("支付通知订单号不匹配")
    expected_channel = _order_channel(order.channel)
    notified_channel = str(params.get("type") or "").strip().lower()
    if notified_channel != expected_channel:
        raise BizError("支付通知渠道不匹配")
    try:
        notified_money = Decimal(str(params.get("money"))).quantize(Decimal("0.01"))
    except Exception as exc:
        raise BizError("支付通知金额无效") from exc
    if notified_money != Decimal(order.amount_cny).quantize(Decimal("0.01")):
        raise BizError("支付通知金额不匹配")
    if params.get("param") not in (None, "", order.order_no):
        raise BizError("支付通知业务参数不匹配")


def _provider_trade_no(db: Session, order: PaymentOrder, params: dict) -> str:
    trade_no = str(params.get("trade_no") or "").strip()
    if not trade_no:
        raise BizError("支付通知缺少平台订单号")
    if order.provider_trade_no and order.provider_trade_no != trade_no:
        raise BizError("充值订单的平台订单号发生冲突")
    other = db.query(PaymentOrder).filter(
        PaymentOrder.provider_trade_no == trade_no,
        PaymentOrder.id != order.id,
    ).first()
    if other:
        raise BizError("平台订单号已被其他订单使用")
    return trade_no


def _parse_provider_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text_value = str(value or "").strip()
        if not text_value:
            return None
        try:
            epoch = float(text_value)
            if epoch > 10_000_000_000:
                epoch /= 1000
            return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            pass
        parsed = None
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
            provider_zone = ZoneInfo(settings.MAPAY_PROVIDER_TIMEZONE)
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
            "支付平台已报告成功，但签名响应中的支付完成时间无法解析，未自动入账",
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
        # A signed success observed before the deadline necessarily represents
        # a payment completed no later than its receipt/query time.
        return "credit", observed_at, None
    return (
        "review",
        None,
        "订单截止后才收到支付成功，且平台未提供可信支付完成时间，未自动入账",
    )


def _record_success_for_review(
    db: Session,
    order: PaymentOrder,
    params: dict,
    *,
    status: str,
    reason: str,
    provider_paid_at: datetime | None,
    validate_payment=None,
) -> bool:
    (validate_payment or _validate_provider_payment)(order, params)
    trade_no = _provider_trade_no(db, order, params)
    if order.credited_at is not None:
        return False
    updates = {
        PaymentOrder.provider_trade_no: trade_no,
        PaymentOrder.provider_status: SUCCESS_STATUS,
        PaymentOrder.status: status,
        PaymentOrder.failure_reason: reason[:160],
        PaymentOrder.last_modified_platform: "system",
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
    validate_payment=None,
    provider_label: str = "码支付",
) -> bool:
    """Credit a cryptographically verified provider success at most once.

    Callers must verify the provider signature before entering this function.
    The wallet and ledger use card-hours; CNY remains only on PaymentOrder.
    """
    validator = validate_payment or _validate_provider_payment
    validator(order, params)
    trade_no = _provider_trade_no(db, order, params)
    if order.credited_at is not None:
        return False

    now = observed_at or utc_now()
    decision, paid_at, reason = _payment_deadline_decision(
        order,
        params,
        observed_at=now,
    )
    if decision != "credit":
        return _record_success_for_review(
            db,
            order,
            params,
            status=decision,
            reason=reason or "支付成功待人工复核",
            provider_paid_at=paid_at,
            validate_payment=validator,
        )

    user_id = order.user_id
    payment_order_id = order.id
    amount_cny = Decimal(order.amount_cny).quantize(Decimal("0.01"))
    card_hours = Decimal(order.card_hours).quantize(Decimal("0.000001"))
    claimed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.credited_at.is_(None),
        or_(
            PaymentOrder.provider_trade_no.is_(None),
            PaymentOrder.provider_trade_no == trade_no,
        ),
    ).update({
        PaymentOrder.provider_trade_no: trade_no,
        PaymentOrder.provider_status: SUCCESS_STATUS,
        PaymentOrder.status: "paid",
        PaymentOrder.failure_reason: None,
        PaymentOrder.paid_at: paid_at or now,
        PaymentOrder.credited_at: now,
        PaymentOrder.last_modified_platform: "system",
    }, synchronize_session=False)
    if claimed == 0:
        db.rollback()
        return False

    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).with_for_update().first()
    if not wallet:
        db.rollback()
        raise BizError("钱包不存在", status_code=404)
    wallet.balance = (
        Decimal(wallet.balance) + card_hours
    ).quantize(Decimal("0.000001"))
    db.add(Ledger(
        user_id=user_id,
        wallet_id=wallet.id,
        type="recharge",
        direction="in",
        amount=card_hours,
        balance_after=wallet.balance,
        ref_payment_order_id=payment_order_id,
        remark=f"{provider_label}人民币 {amount_cny:.2f} 元兑换 {card_hours} 卡时",
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


def handle_notification(db: Session, params: dict) -> bool:
    if not verify_params(params):
        raise BizError("支付通知签名无效")
    order_no = str(params.get("out_trade_no") or "")
    order = db.query(PaymentOrder).filter(PaymentOrder.order_no == order_no).first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    status = str(params.get("trade_status") or "")
    order.provider_status = status[:64]
    order.last_modified_platform = "system"
    if status != SUCCESS_STATUS:
        if status in FINAL_PROVIDER_FAILURES and order.credited_at is None:
            order.status = "failed"
            order.failure_reason = f"支付平台返回失败状态：{status}"[:160]
        else:
            _expire_order_if_due(order)
        db.commit()
        return False

    received_at = utc_now()
    provider_paid_at, time_was_supplied = _provider_paid_at(params)
    if received_at > order.expires_at and (not time_was_supplied or provider_paid_at is None):
        # Notifications do not normally contain endtime.  For a late callback,
        # ask the provider for a separately signed order record before deciding.
        try:
            queried = _query_provider_payload(order)
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


def _provider_query_configured() -> bool:
    return bool(
        settings.PAYMENT_SERVICE_ENABLED
        and settings.MAPAY_ENABLED
        and settings.MAPAY_PID.strip()
        and Path(settings.MAPAY_MERCHANT_PRIVATE_KEY_PATH).expanduser().is_file()
        and Path(settings.MAPAY_PLATFORM_PUBLIC_KEY_PATH).expanduser().is_file()
    )


def _query_provider_payload(order: PaymentOrder) -> dict:
    if not _provider_query_configured():
        raise BizError("码支付V2尚未完成密钥配置", status_code=503)
    params = {
        "pid": settings.MAPAY_PID,
        "out_trade_no": order.order_no,
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "sign_type": "RSA",
    }
    params["sign"] = sign_params(params)
    url = settings.MAPAY_BASE_URL.rstrip("/") + "/api/pay/query"
    try:
        response = httpx.post(url, data=params, timeout=settings.MAPAY_HTTP_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise BizError("支付平台订单查询失败，请稍后重试", status_code=502) from exc
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise BizError("支付平台暂未确认该订单", status_code=409)
    if not _verify_query_response(payload):
        raise BizError("支付平台查询响应签名无效", status_code=502)
    if str(payload.get("out_trade_no") or "") != order.order_no:
        raise BizError("支付平台查询订单号不匹配", status_code=502)
    return payload


def _provider_reports_success(payload: dict) -> bool:
    try:
        return int(payload.get("status") or 0) == 1
    except (TypeError, ValueError):
        return str(payload.get("trade_status") or "") == SUCCESS_STATUS


def query_provider_and_reconcile(db: Session, order: PaymentOrder) -> dict:
    if order.credited_at is not None:
        return _payment_out(order)
    _persist_order_expiry(db, order)

    payload = _query_provider_payload(order)
    if _provider_reports_success(payload):
        normalized = dict(payload)
        normalized["trade_status"] = SUCCESS_STATUS
        credit_verified_payment(db, order, normalized, observed_at=utc_now())
    else:
        order.provider_status = str(payload.get("status") or "0")
        order.last_modified_platform = "system"
        if order.status not in {"review", "late_paid_review"}:
            _expire_order_if_due(order)
        db.commit()
    db.refresh(order)
    return _payment_out(order)
