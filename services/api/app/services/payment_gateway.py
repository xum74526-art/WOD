import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import DEFAULT_SECRET_KEY, settings
from app.services import mapay, qixiangpay


def provider_configured() -> bool:
    """Return readiness for the only gateway allowed to create new payments."""
    return qixiangpay.provider_configured()


def public_config() -> dict:
    config = qixiangpay.public_config()
    config["readiness_errors"] = payment_readiness_errors()
    config["legacy_mapay_reconciliation_enabled"] = bool(
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED
    )
    return config


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def payment_readiness_errors() -> list[str]:
    """Return stable, non-secret deployment blockers for payment capabilities.

    ``PAYMENT_SERVICE_ENABLED`` is the new-collection kill switch.  Historical
    callbacks, queries, reconciliation and refunds deliberately remain
    available when that switch is off, provided the provider itself and the
    credentials needed for those close-out operations stay configured.
    """
    errors: list[str] = []
    if settings.QIXIANGPAY_ENABLED and settings.MAPAY_ENABLED:
        errors.append("multiple_new_collection_providers")
    if settings.MAPAY_ENABLED:
        errors.append("mapay_new_collection_retired")
    if settings.MAPAY_LEGACY_RECONCILIATION_ENABLED:
        if not str(settings.MAPAY_PID or "").strip():
            errors.append("mapay_pid_missing")
        if not mapay.official_gateway_base_url_configured(settings.MAPAY_BASE_URL):
            errors.append("mapay_base_url_invalid")
        if not mapay.merchant_private_key_configured():
            errors.append("mapay_merchant_private_key_invalid")
        if not mapay.platform_public_key_configured():
            errors.append("mapay_platform_public_key_invalid")
        try:
            ZoneInfo(str(settings.MAPAY_PROVIDER_TIMEZONE or ""))
        except (ZoneInfoNotFoundError, ValueError):
            errors.append("mapay_timezone_invalid")
        try:
            mapay_timeout = float(settings.MAPAY_HTTP_TIMEOUT)
        except (TypeError, ValueError):
            mapay_timeout = math.nan
        if not math.isfinite(mapay_timeout) or not 1.0 <= mapay_timeout <= 55.0:
            errors.append("mapay_http_timeout_invalid")

    collection_requested = bool(settings.PAYMENT_SERVICE_ENABLED)
    if collection_requested and not settings.QIXIANGPAY_ENABLED:
        errors.append("qixiangpay_not_enabled")
    if settings.QIXIANGPAY_ENABLED:
        if not str(settings.QIXIANGPAY_PID or "").strip():
            errors.append("qixiangpay_pid_missing")
        if not str(settings.QIXIANGPAY_KEY or ""):
            errors.append("qixiangpay_key_missing")
        if not qixiangpay.official_gateway_base_url_configured(
            settings.QIXIANGPAY_BASE_URL
        ):
            errors.append("qixiangpay_base_url_invalid")
        try:
            ZoneInfo(str(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        except (ZoneInfoNotFoundError, ValueError):
            errors.append("qixiangpay_timezone_invalid")
    if collection_requested and settings.QIXIANGPAY_ENABLED:
        if not settings.DIRECT_TRADE_ENABLED:
            errors.append("direct_trade_not_enabled")
        if not qixiangpay.canonical_notify_url_configured(
            settings.QIXIANGPAY_NOTIFY_URL
        ):
            errors.append("qixiangpay_notify_url_invalid")
        if not qixiangpay.dedicated_return_url_configured(
            settings.QIXIANGPAY_RETURN_URL
        ):
            errors.append("qixiangpay_return_url_invalid")
        if not qixiangpay.canonical_public_api_base_url_configured(
            settings.QIXIANGPAY_PUBLIC_API_BASE_URL
        ):
            errors.append("qixiangpay_public_api_base_url_invalid")
        if not qixiangpay.configured_payment_types():
            errors.append("qixiangpay_payment_types_missing")
        if str(settings.QIXIANGPAY_DEVICE or "").strip().lower() != "jump":
            errors.append("qixiangpay_device_must_be_jump")
        if not qixiangpay.checkout_host_configuration_valid():
            errors.append("payment_checkout_allowed_hosts_invalid")
        if settings.SECRET_KEY == DEFAULT_SECRET_KEY or not str(settings.SECRET_KEY).strip():
            errors.append("default_secret_key")
        if not _finite_positive(settings.CARD_HOUR_RMB_RATE):
            errors.append("card_hour_rmb_rate_invalid")
        if not _finite_positive(settings.QIXIANGPAY_MIN_AMOUNT_CNY):
            errors.append("qixiangpay_min_amount_invalid")
        if (
            not _finite_positive(settings.QIXIANGPAY_MAX_AMOUNT_CNY)
            or float(settings.QIXIANGPAY_MAX_AMOUNT_CNY)
            < float(settings.QIXIANGPAY_MIN_AMOUNT_CNY)
        ):
            errors.append("qixiangpay_amount_range_invalid")
        if not 1 <= int(settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER) <= 20:
            errors.append("payment_pending_limit_invalid")
        if not _finite_positive(settings.PAYMENT_DAILY_RECHARGE_LIMIT_CNY):
            errors.append("payment_daily_limit_invalid")
    if settings.QIXIANGPAY_REFUND_ENABLED:
        if not settings.QIXIANGPAY_ENABLED:
            errors.append("qixiangpay_refund_without_provider")
        if not qixiangpay.provider_refund_configured():
            errors.append("qixiangpay_refund_not_ready")

    if settings.PAYMENT_RECONCILIATION_ENABLED:
        if not settings.QIXIANGPAY_ENABLED:
            errors.append("reconciliation_without_qixiangpay")
        if not 1 <= int(settings.PAYMENT_RECONCILIATION_BATCH_SIZE) <= 50:
            errors.append("reconciliation_batch_size_invalid")
        if not 30 <= int(settings.PAYMENT_RECONCILIATION_INTERVAL_SECONDS) <= 3600:
            errors.append("reconciliation_interval_invalid")
        if not 10 <= int(settings.PAYMENT_RECONCILIATION_MIN_AGE_SECONDS) <= 3600:
            errors.append("reconciliation_min_age_invalid")
        if (
            int(settings.PAYMENT_RECONCILIATION_MAX_AGE_SECONDS)
            < int(settings.PAYMENT_RECONCILIATION_MIN_AGE_SECONDS)
        ):
            errors.append("reconciliation_age_range_invalid")
    return sorted(set(errors))


def assert_payment_configuration_safe() -> None:
    errors = payment_readiness_errors()
    if errors:
        raise RuntimeError(
            "Payment capabilities are not safe to start: " + ", ".join(errors)
        )
