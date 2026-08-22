"""QiXiang Pay wallet-recharge adapter.

The provider uses the EasyPay-compatible MD5 protocol documented at
https://qixiangpay.cn/doc_old.html. Credentials never leave the backend.
Wallet crediting reuses the existing transactional/idempotent accounting
boundary after this adapter has authenticated and validated the provider data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import PaymentOrder
from app.services.mapay import (
    _payment_out,
    _persist_order_expiry,
    credit_verified_payment,
    utc_now,
)
from app.utils.response import BizError


PROVIDER = "qixiangpay"
SUCCESS_STATUS = "TRADE_SUCCESS"
SUPPORTED_PAYMENT_TYPES = frozenset({"alipay", "wxpay"})


def canonicalize(params: dict) -> str:
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
    secret = settings.QIXIANGPAY_KEY.strip()
    if not secret:
        raise BizError("七象支付商户密钥尚未配置", status_code=503)
    return hashlib.md5((canonicalize(params) + secret).encode("utf-8")).hexdigest()


def verify_params(params: dict) -> bool:
    supplied = str(params.get("sign") or "").strip().lower()
    if len(supplied) != 32:
        return False
    try:
        expected = sign_params(params)
    except BizError:
        return False
    return hmac.compare_digest(supplied, expected)


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
    return min(max(int(settings.QIXIANGPAY_CHECKOUT_TTL_SECONDS), 60), 1800)


def provider_configured() -> bool:
    return bool(
        settings.PAYMENT_SERVICE_ENABLED
        and settings.QIXIANGPAY_ENABLED
        and settings.QIXIANGPAY_PID.strip()
        and settings.QIXIANGPAY_KEY.strip()
        and settings.QIXIANGPAY_NOTIFY_URL.startswith("https://")
        and settings.QIXIANGPAY_RETURN_URL.startswith("https://")
        and configured_payment_types()
    )


def public_config() -> dict:
    return {
        "provider": PROVIDER,
        "enabled": provider_configured(),
        "pid_configured": bool(settings.QIXIANGPAY_PID.strip()),
        "sign_version": "MD5",
        "card_hour_rmb_rate": float(settings.CARD_HOUR_RMB_RATE),
        "min_amount_cny": float(settings.QIXIANGPAY_MIN_AMOUNT_CNY),
        "max_amount_cny": float(settings.QIXIANGPAY_MAX_AMOUNT_CNY),
        "checkout_mode": "hosted_page",
        "checkout_ttl_seconds": checkout_ttl_seconds(),
        "payment_types": list(configured_payment_types()),
    }


def _require_payment_type(payment_type: str | None) -> str:
    normalized = str(payment_type or "").strip().lower()
    if normalized not in SUPPORTED_PAYMENT_TYPES:
        raise BizError("不支持的支付方式", status_code=400)
    if normalized not in configured_payment_types():
        raise BizError("该支付方式当前不可用", status_code=400)
    return normalized


def _provider_checkout_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    configured_host = (urlparse(settings.QIXIANGPAY_BASE_URL).hostname or "").lower()
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise BizError("七象支付未返回安全收银台地址", status_code=502)
    if hostname != configured_host and not hostname.endswith(".payqixiang.cn"):
        raise BizError("七象支付返回了非受信收银台地址", status_code=502)
    return url


def _create_provider_checkout(order: PaymentOrder) -> tuple[str, str | None]:
    fields = {
        "pid": settings.QIXIANGPAY_PID,
        "type": order.channel,
        "out_trade_no": order.order_no,
        "notify_url": settings.QIXIANGPAY_NOTIFY_URL,
        "return_url": settings.QIXIANGPAY_RETURN_URL,
        "name": "KAI钱包卡时充值",
        "money": f"{order.amount_cny:.2f}",
        "clientip": "127.0.0.1",
        "device": settings.QIXIANGPAY_DEVICE or "jump",
        "param": order.order_no,
        "sign_type": "MD5",
    }
    fields["sign"] = sign_params(fields)
    try:
        response = httpx.post(
            settings.QIXIANGPAY_BASE_URL.rstrip("/") + "/mapi.php",
            data=fields,
            headers={"Accept": "application/json"},
            timeout=settings.QIXIANGPAY_HTTP_TIMEOUT,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise BizError("七象支付下单失败，请稍后重试", status_code=502) from exc
    if not isinstance(payload, dict) or str(payload.get("code")) != "1":
        raise BizError("七象支付暂未受理该订单", status_code=502)
    checkout_url = _provider_checkout_url(payload.get("payurl") or payload.get("qrcode"))
    trade_no = str(payload.get("trade_no") or "").strip() or None
    return checkout_url, trade_no


def create_recharge_order(
    db: Session,
    user_id: int,
    amount_cny: Decimal,
    *,
    payment_type: str | None,
) -> dict:
    if not provider_configured():
        raise BizError("七象支付尚未完成云端回调配置", status_code=503)
    channel = _require_payment_type(payment_type)
    minimum = Decimal(str(settings.QIXIANGPAY_MIN_AMOUNT_CNY)).quantize(Decimal("0.01"))
    maximum = Decimal(str(settings.QIXIANGPAY_MAX_AMOUNT_CNY)).quantize(Decimal("0.01"))
    amount = Decimal(str(amount_cny)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < minimum or amount > maximum:
        raise BizError(f"充值金额须在 {minimum:.2f} 至 {maximum:.2f} 元之间")
    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE)).quantize(Decimal("0.000001"))
    if rate <= 0:
        raise BizError("卡时兑换率配置无效", status_code=503)

    order = PaymentOrder(
        order_no=f"KAIQ{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}",
        user_id=user_id,
        provider=PROVIDER,
        channel=channel,
        status="pending",
        amount_cny=amount,
        card_hours=(amount / rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        card_hour_rate=rate,
        checkout_token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        expires_at=utc_now() + timedelta(seconds=checkout_ttl_seconds()),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    try:
        checkout_url, trade_no = _create_provider_checkout(order)
        if trade_no:
            order.provider_trade_no = trade_no
        db.commit()
    except BizError as exc:
        order.status = "failed"
        order.failure_reason = exc.msg[:160]
        db.commit()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise BizError("七象支付平台订单号发生冲突", status_code=409) from exc
    return _payment_out(order, checkout_url)


def get_owned_order(db: Session, user_id: int, order_no: str) -> PaymentOrder:
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
        PaymentOrder.user_id == user_id,
        PaymentOrder.provider == PROVIDER,
    ).first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    return order


def payment_status(db: Session, user_id: int, order_no: str) -> dict:
    order = get_owned_order(db, user_id, order_no)
    _persist_order_expiry(db, order)
    return _payment_out(order)


def _validate_provider_payment(order: PaymentOrder, params: dict) -> None:
    if order.provider != PROVIDER:
        raise BizError("充值订单支付平台不匹配")
    if str(params.get("pid") or "") != settings.QIXIANGPAY_PID:
        raise BizError("支付通知商户号不匹配")
    if str(params.get("out_trade_no") or "") != order.order_no:
        raise BizError("支付通知订单号不匹配")
    if str(params.get("type") or "").strip().lower() != str(order.channel or "").lower():
        raise BizError("支付通知渠道不匹配")
    try:
        money = Decimal(str(params.get("money"))).quantize(Decimal("0.01"))
    except Exception as exc:
        raise BizError("支付通知金额无效") from exc
    if money != Decimal(order.amount_cny).quantize(Decimal("0.01")):
        raise BizError("支付通知金额不匹配")
    if params.get("param") not in (None, "", order.order_no):
        raise BizError("支付通知业务参数不匹配")


def handle_notification(db: Session, params: dict) -> bool:
    if not verify_params(params):
        raise BizError("支付通知签名无效")
    order_no = str(params.get("out_trade_no") or "")
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
        PaymentOrder.provider == PROVIDER,
    ).first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    _validate_provider_payment(order, params)
    status = str(params.get("trade_status") or "")
    order.provider_status = status[:64]
    if status != SUCCESS_STATUS:
        db.commit()
        return False
    credit_verified_payment(
        db,
        order,
        params,
        observed_at=utc_now(),
        validate_payment=_validate_provider_payment,
        provider_label="七象支付",
    )
    return True


def _query_provider_payload(order: PaymentOrder) -> dict:
    if not provider_configured():
        raise BizError("七象支付尚未完成云端回调配置", status_code=503)
    try:
        response = httpx.get(
            settings.QIXIANGPAY_BASE_URL.rstrip("/") + "/api.php",
            params={
                "act": "order",
                "pid": settings.QIXIANGPAY_PID,
                "key": settings.QIXIANGPAY_KEY,
                "out_trade_no": order.order_no,
            },
            headers={"Accept": "application/json"},
            timeout=settings.QIXIANGPAY_HTTP_TIMEOUT,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise BizError("七象支付订单查询失败，请稍后重试", status_code=502) from exc
    if not isinstance(payload, dict) or str(payload.get("code")) != "1":
        raise BizError("七象支付暂未确认该订单", status_code=409)
    _validate_provider_payment(order, payload)
    return payload


def query_provider_and_reconcile(db: Session, order: PaymentOrder) -> dict:
    if order.credited_at is not None:
        return _payment_out(order)
    _persist_order_expiry(db, order)
    payload = _query_provider_payload(order)
    try:
        paid = int(payload.get("status") or 0) == 1
    except (TypeError, ValueError):
        paid = False
    if paid:
        normalized = dict(payload)
        normalized["trade_status"] = SUCCESS_STATUS
        credit_verified_payment(
            db,
            order,
            normalized,
            observed_at=utc_now(),
            validate_payment=_validate_provider_payment,
            provider_label="七象支付",
        )
    else:
        order.provider_status = str(payload.get("status") or "0")[:64]
        db.commit()
    db.refresh(order)
    return _payment_out(order)
