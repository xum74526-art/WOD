"""Read-only Ping++ Test/Live configuration preflight."""

import argparse
import json
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization

from app.config import settings


def _key_check(value: str, *, private: bool) -> tuple[bool, str]:
    if not value.strip():
        return False, "missing"
    try:
        pem = value.strip().replace("\\n", "\n").encode()
        if private:
            serialization.load_pem_private_key(pem, password=None)
        else:
            serialization.load_pem_public_key(pem)
    except (TypeError, ValueError):
        return False, "invalid PEM"
    return True, "valid PEM"


def preflight() -> dict:
    api = urlparse(settings.PINGXX_API_BASE_URL)
    callback_url = f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/v1/payments/webhooks/pingxx"
    callback = urlparse(callback_url)
    public_ok, public_detail = _key_check(settings.PINGXX_PUBLIC_KEY, private=False)
    private_ok, private_detail = _key_check(settings.PINGXX_MERCHANT_PRIVATE_KEY, private=True)
    expected_prefix = "sk_live_" if settings.PINGXX_LIVE_MODE else "sk_test_"
    checks = [
        {"name": "provider_enabled", "ok": settings.PAYMENT_PROVIDER_ENABLED, "detail": str(settings.PAYMENT_PROVIDER_ENABLED)},
        {"name": "provider_name", "ok": settings.PAYMENT_PROVIDER == "pingxx", "detail": settings.PAYMENT_PROVIDER},
        {"name": "api_endpoint", "ok": api.scheme == "https" and api.netloc == "api.pingxx.com", "detail": settings.PINGXX_API_BASE_URL},
        {"name": "api_key_mode", "ok": settings.PINGXX_API_KEY.startswith(expected_prefix), "detail": expected_prefix + "…"},
        {"name": "app_id", "ok": settings.PINGXX_APP_ID.startswith("app_"), "detail": "present" if settings.PINGXX_APP_ID else "missing"},
        {"name": "pingxx_public_key", "ok": public_ok, "detail": public_detail},
        {"name": "webhook_https", "ok": callback.scheme == "https" and bool(callback.netloc), "detail": callback_url},
        {"name": "default_channel", "ok": bool(settings.PINGXX_DEFAULT_CHANNEL), "detail": settings.PINGXX_DEFAULT_CHANNEL},
    ]
    if settings.PINGXX_REQUEST_SIGNING_ENABLED:
        checks.append({"name": "merchant_private_key", "ok": private_ok, "detail": private_detail})
    if settings.APP_ENV.casefold() == "production":
        checks.extend([
            {"name": "live_mode", "ok": settings.PINGXX_LIVE_MODE, "detail": str(settings.PINGXX_LIVE_MODE)},
            {"name": "request_signing", "ok": settings.PINGXX_REQUEST_SIGNING_ENABLED, "detail": str(settings.PINGXX_REQUEST_SIGNING_ENABLED)},
        ])
    return {
        "ok": all(item["ok"] for item in checks),
        "mode": "live" if settings.PINGXX_LIVE_MODE else "test",
        "callback_url": callback_url,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Ping++ payment configuration")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = preflight()
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            print(f"[{'OK' if item['ok'] else 'FAIL'}] {item['name']}: {item['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
