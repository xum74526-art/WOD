from app.config import settings
from app.providers.contracts import (
    DisabledKycProvider,
    DisabledPaymentProvider,
    DisabledStorageProvider,
    KycProvider,
    PaymentProvider,
    StorageProvider,
)
from app.providers.pingxx import PingxxProvider


def _requested(value: str) -> str:
    return (value or "disabled").strip().casefold()


def _reason(requested: str, legacy_enabled: bool) -> str:
    if requested != "disabled":
        return "adapter_missing"
    if legacy_enabled:
        return "provider_name_required"
    return "not_configured"


def payment_provider() -> PaymentProvider:
    requested = _requested(settings.PAYMENT_PROVIDER)
    if requested in {"pingxx", "ping++"}:
        return PingxxProvider(
            enabled=settings.PAYMENT_PROVIDER_ENABLED,
            api_base_url=settings.PINGXX_API_BASE_URL,
            api_key=settings.PINGXX_API_KEY,
            app_id=settings.PINGXX_APP_ID,
            pingxx_public_key=settings.PINGXX_PUBLIC_KEY,
            merchant_private_key=settings.PINGXX_MERCHANT_PRIVATE_KEY,
            request_signing_enabled=settings.PINGXX_REQUEST_SIGNING_ENABLED,
            live_mode=settings.PINGXX_LIVE_MODE,
            default_channel=settings.PINGXX_DEFAULT_CHANNEL,
            frontend_base_url=settings.FRONTEND_BASE_URL,
            timeout_seconds=settings.PINGXX_HTTP_TIMEOUT_SECONDS,
        )
    return DisabledPaymentProvider(requested, _reason(requested, settings.PAYMENT_PROVIDER_ENABLED))


def kyc_provider() -> KycProvider:
    requested = _requested(settings.KYC_PROVIDER)
    # Add real adapters here, for example: if requested == "aliyun_kyc": return AliyunKycProvider(...)
    return DisabledKycProvider(requested, _reason(requested, settings.KYC_PROVIDER_ENABLED))


def storage_provider() -> StorageProvider:
    requested = _requested(settings.OBJECT_STORAGE_PROVIDER)
    # Add real adapters here, for example: if requested == "aliyun_oss": return AliyunOssProvider(...)
    return DisabledStorageProvider(requested, _reason(requested, settings.OBJECT_STORAGE_ENABLED))


def integration_descriptors() -> dict[str, dict]:
    return {
        "payment": payment_provider().descriptor.as_dict(),
        "kyc": kyc_provider().descriptor.as_dict(),
        "object_storage": storage_provider().descriptor.as_dict(),
    }
