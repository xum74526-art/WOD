from app.core.config import settings
from app.services import mapay, qixiangpay


def provider_configured() -> bool:
    if settings.QIXIANGPAY_ENABLED:
        return qixiangpay.provider_configured()
    return mapay.provider_configured()


def public_config() -> dict:
    if settings.QIXIANGPAY_ENABLED:
        return qixiangpay.public_config()
    return mapay.public_config()
