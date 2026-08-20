import base64
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.providers.contracts import (
    PaymentNotification,
    PaymentProvider,
    PaymentRequest,
    PaymentSession,
    ProviderDescriptor,
    ProviderUnavailable,
    RefundSession,
)

SUPPORTED_WEB_CHANNELS = {
    "alipay_pc_direct",
    "alipay_wap",
    "wx_wap",
    "upacp_pc",
    "upacp_wap",
}


def _pem(value: str) -> bytes:
    return value.strip().replace("\\n", "\n").encode()


def _amount_in_fen(value: Decimal) -> int:
    if value <= 0 or value != value.quantize(Decimal("0.01")):
        raise ProviderUnavailable("payment", "pingxx", "amount_precision_not_supported")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _amount_in_yuan(value: Any) -> Decimal:
    try:
        return (Decimal(str(value)) / Decimal("100")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_amount") from exc


class PingxxProvider(PaymentProvider):
    """Ping++ Charge/Refund adapter using the documented JSON REST API."""

    def __init__(
        self,
        *,
        enabled: bool,
        api_base_url: str,
        api_key: str,
        app_id: str,
        pingxx_public_key: str,
        merchant_private_key: str,
        request_signing_enabled: bool,
        live_mode: bool,
        default_channel: str,
        frontend_base_url: str,
        timeout_seconds: float,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.app_id = app_id.strip()
        self._pingxx_public_key_text = pingxx_public_key
        self._merchant_private_key_text = merchant_private_key
        self.request_signing_enabled = request_signing_enabled
        self.live_mode = live_mode
        self.default_channel = default_channel.strip()
        self.frontend_base_url = frontend_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        missing = [
            name
            for name, value in (
                ("PINGXX_API_KEY", self.api_key),
                ("PINGXX_APP_ID", self.app_id),
                ("PINGXX_PUBLIC_KEY", pingxx_public_key.strip()),
                ("PINGXX_DEFAULT_CHANNEL", self.default_channel),
            )
            if not value
        ]
        if request_signing_enabled and not merchant_private_key.strip():
            missing.append("PINGXX_MERCHANT_PRIVATE_KEY")
        api_url = urlparse(self.api_base_url)
        invalid_api_url = api_url.scheme != "https" or api_url.netloc != "api.pingxx.com"
        expected_prefix = "sk_live_" if live_mode else "sk_test_"
        key_mode_mismatch = bool(self.api_key) and not self.api_key.startswith(expected_prefix)
        configured = enabled and not missing and not invalid_api_url and not key_mode_mismatch
        self.descriptor = ProviderDescriptor(
            kind="payment",
            provider="pingxx",
            status="configured" if configured else "degraded",
            configured=configured,
            capabilities=(
                "charge",
                "h5_checkout",
                "rsa_sha256_webhook",
                "charge_query",
                "refund",
                "test_mode" if not live_mode else "live_mode",
                "double_entry_ledger",
            ),
            reason=(
                None
                if configured
                else "provider_disabled"
                if not enabled
                else "invalid_api_url"
                if invalid_api_url
                else "api_key_mode_mismatch"
                if key_mode_mismatch
                else "missing:" + ",".join(missing)
            ),
        )

    def _ensure_configured(self) -> None:
        if not self.descriptor.configured:
            raise ProviderUnavailable("payment", "pingxx", self.descriptor.reason or "not_configured")

    def _private_key(self):
        try:
            return serialization.load_pem_private_key(
                _pem(self._merchant_private_key_text), password=None
            )
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailable("payment", "pingxx", "invalid_merchant_private_key") from exc

    def _public_key(self):
        try:
            return serialization.load_pem_public_key(_pem(self._pingxx_public_key_text))
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailable("payment", "pingxx", "invalid_pingxx_public_key") from exc

    def _headers(self, *, body: bytes | None, request_uri: str) -> dict[str, str]:
        timestamp = str(int(time.time()))
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Accept-Language": "zh-CN",
            "Content-Type": "application/json; charset=UTF-8",
            "Pingplusplus-Request-Timestamp": timestamp,
            "User-Agent": "KAI-Pingxx/1.0",
        }
        if self.request_signing_enabled:
            signing_data = (body.decode() if body else "") + request_uri + timestamp
            signature = self._private_key().sign(
                signing_data.encode(), padding.PKCS1v15(), hashes.SHA256()
            )
            headers["Pingplusplus-Signature"] = base64.b64encode(signature).decode()
        return headers

    def _request(self, method: str, request_uri: str, payload: dict | None = None) -> dict:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            if payload is not None
            else None
        )
        try:
            response = httpx.request(
                method,
                f"{self.api_base_url}{request_uri}",
                content=body,
                headers=self._headers(body=body, request_uri=request_uri),
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("payment", "pingxx", "request_timeout") from exc
        except httpx.HTTPStatusError as exc:
            reason = "api_rejected_request"
            try:
                error = exc.response.json().get("error") or {}
                reason = str(error.get("code") or reason)[:64]
            except (ValueError, AttributeError):
                pass
            raise ProviderUnavailable("payment", "pingxx", reason) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable("payment", "pingxx", "invalid_api_response") from exc
        if not isinstance(data, dict):
            raise ProviderUnavailable("payment", "pingxx", "invalid_api_response")
        return data

    def _extra(self, channel: str, return_url: str) -> dict[str, str]:
        if channel == "alipay_pc_direct":
            return {"success_url": return_url}
        if channel == "alipay_wap":
            return {"success_url": return_url, "cancel_url": return_url}
        if channel in {"wx_wap", "upacp_pc", "upacp_wap"}:
            return {"result_url": return_url}
        return {}

    def create_checkout(self, request: PaymentRequest) -> PaymentSession:
        self._ensure_configured()
        if request.currency.upper() != "CNY":
            raise ProviderUnavailable("payment", "pingxx", "currency_not_supported")
        channel = request.channel or self.default_channel
        if channel not in SUPPORTED_WEB_CHANNELS:
            raise ProviderUnavailable("payment", "pingxx", "channel_not_supported")
        expire_at = int(time.time()) + 30 * 60
        payload = {
            "order_no": request.payment_no,
            "amount": _amount_in_fen(request.amount),
            "app": {"id": self.app_id},
            "channel": channel,
            "currency": "cny",
            "client_ip": request.client_ip,
            "subject": request.purpose[:32],
            "body": request.purpose[:128],
            "time_expire": expire_at,
            "extra": self._extra(channel, request.return_url),
            "metadata": {
                "payment_no": request.payment_no,
                "user_id": str(request.user_id),
                "idempotency_key": request.idempotency_key,
            },
        }
        charge = self._request("POST", "/v1/charges", payload)
        if charge.get("object") != "charge" or not str(charge.get("id", "")).startswith("ch_"):
            raise ProviderUnavailable("payment", "pingxx", "invalid_charge_response")
        if charge.get("order_no") != request.payment_no:
            raise ProviderUnavailable("payment", "pingxx", "charge_order_mismatch")
        if int(charge.get("amount", -1)) != payload["amount"]:
            raise ProviderUnavailable("payment", "pingxx", "charge_amount_mismatch")
        charge_livemode = bool(charge.get("livemode"))
        if charge_livemode != self.live_mode:
            raise ProviderUnavailable("payment", "pingxx", "charge_mode_mismatch")
        timestamp = int(charge.get("time_expire") or expire_at)
        return PaymentSession(
            provider_reference=str(charge["id"]),
            checkout_url=f"{self.frontend_base_url}/payment/{request.payment_no}",
            expires_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            client_payload=charge,
        )

    def _retrieve_charge(self, charge_id: str) -> dict:
        if not charge_id.startswith("ch_"):
            raise ProviderUnavailable("payment", "pingxx", "invalid_charge_id")
        return self._request("GET", f"/v1/charges/{quote(charge_id, safe='')}")

    def query_payment(self, provider_reference: str) -> PaymentNotification:
        """Return a normalized state after querying Ping++ itself.

        This is the missed-webhook recovery path.  It deliberately does not
        accept any state supplied by the browser.
        """
        self._ensure_configured()
        charge = self._retrieve_charge(provider_reference)
        if charge.get("object") != "charge" or charge.get("id") != provider_reference:
            raise ValueError("charge_query_mismatch")
        if charge.get("app") != self.app_id or bool(charge.get("livemode")) != self.live_mode:
            raise ValueError("charge_app_or_mode_mismatch")
        payment_no = str(charge.get("order_no") or "")
        if not payment_no:
            raise ValueError("missing_payment_no")
        succeeded = bool(charge.get("paid"))
        time_paid = str(charge.get("time_paid") or "pending")
        return PaymentNotification(
            event_type="charge.succeeded" if succeeded else "charge.pending",
            event_id=f"query:{provider_reference}:{time_paid}",
            payment_no=payment_no,
            provider_reference=provider_reference,
            amount=_amount_in_yuan(charge.get("amount")),
            currency=str(charge.get("currency") or "cny").upper(),
            succeeded=succeeded,
            raw_status="paid" if succeeded else "unpaid",
        )

    def _verify_webhook_signature(self, raw_body: bytes, signature: str) -> None:
        if not signature:
            raise ValueError("missing_signature")
        try:
            decoded = base64.b64decode(signature, validate=True)
            self._public_key().verify(decoded, raw_body, padding.PKCS1v15(), hashes.SHA256())
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("invalid_signature") from exc

    def verify_notification(self, raw_body: bytes, signature: str) -> PaymentNotification:
        self._ensure_configured()
        self._verify_webhook_signature(raw_body, signature)
        try:
            event = json.loads(raw_body)
            event_type = str(event["type"])
            obj = event["data"]["object"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("invalid_event") from exc
        if event_type not in {"charge.succeeded", "refund.succeeded"} or not isinstance(obj, dict):
            raise ValueError("unsupported_event")
        if bool(event.get("livemode")) != self.live_mode or bool(obj.get("livemode")) != self.live_mode:
            raise ValueError("event_mode_mismatch")
        event_id = str(event.get("id") or "")
        if not event_id.startswith("evt_"):
            raise ValueError("invalid_event_id")

        if event_type == "charge.succeeded":
            charge_id = str(obj.get("id") or "")
            payment_no = str(obj.get("order_no") or "")
            refund_reference = None
            raw_status = "paid" if obj.get("paid") else "unpaid"
            webhook_amount = obj.get("amount")
        else:
            charge_value = obj.get("charge")
            charge_id = str(charge_value.get("id") if isinstance(charge_value, dict) else charge_value or "")
            payment_no = ""
            refund_reference = str(obj.get("id") or "")
            raw_status = str(obj.get("status") or ("succeeded" if obj.get("succeed") else ""))
            webhook_amount = obj.get("amount")

        charge = self._retrieve_charge(charge_id)
        if charge.get("object") != "charge" or charge.get("id") != charge_id:
            raise ValueError("charge_query_mismatch")
        if charge.get("app") != self.app_id or bool(charge.get("livemode")) != self.live_mode:
            raise ValueError("charge_app_or_mode_mismatch")
        payment_no = str(charge.get("order_no") or payment_no)
        if not payment_no:
            raise ValueError("missing_payment_no")
        if event_type == "charge.succeeded" and not charge.get("paid"):
            raise ValueError("charge_query_not_paid")
        amount_value = webhook_amount if webhook_amount is not None else charge.get("amount")
        return PaymentNotification(
            event_type=event_type,
            event_id=event_id,
            payment_no=payment_no,
            provider_reference=charge_id,
            amount=_amount_in_yuan(amount_value),
            currency=str(charge.get("currency") or "cny").upper(),
            succeeded=True,
            raw_status=raw_status,
            refund_reference=refund_reference,
        )

    def create_refund(
        self,
        *,
        provider_reference: str,
        refund_no: str,
        amount: Decimal,
        reason: str,
    ) -> RefundSession:
        self._ensure_configured()
        payload = {
            "amount": _amount_in_fen(amount),
            "description": reason[:255],
            "metadata": {"refund_no": refund_no},
        }
        refund = self._request(
            "POST",
            f"/v1/charges/{quote(provider_reference, safe='')}/refunds",
            payload,
        )
        refund_id = str(refund.get("id") or "")
        if refund.get("object") != "refund" or not refund_id.startswith("re_"):
            raise ProviderUnavailable("payment", "pingxx", "invalid_refund_response")
        return RefundSession(
            provider_reference=refund_id,
            status=str(refund.get("status") or "pending"),
        )
