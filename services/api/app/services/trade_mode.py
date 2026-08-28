from app.core.config import settings
from app.core.sensitive import sensitive_capability_enabled, sensitive_security_errors
from app.utils.response import BizError


INQUIRY_ONLY_MESSAGE = "当前仅支持提交需求并人工确认"
MATCHMAKING_DISABLED_MESSAGE = "需求撮合服务暂未开放"
RECHARGE_DISABLED_MESSAGE = "充值服务暂未开放"
WITHDRAWAL_DISABLED_MESSAGE = "提现服务暂未开放"

COMMERCE_MODE_DIRECT_TRADE = "direct_trade"
COMMERCE_MODE_MATCHMAKING = "matchmaking"
COMMERCE_MODE_HISTORY_ONLY = "history_only"


def direct_trade_enabled() -> bool:
    return settings.DIRECT_TRADE_ENABLED is True


def matchmaking_enabled() -> bool:
    return settings.MATCHMAKING_ENABLED is True


def credential_escrow_enabled() -> bool:
    return (
        matchmaking_enabled()
        and settings.MATCHMAKING_CREDENTIAL_ESCROW_ENABLED is True
        and not sensitive_security_errors()
    )


def commerce_mode() -> str:
    """Return the most permissive server-authorised interaction mode.

    Explicit ``is True`` checks are intentional: unexpected or missing values
    must never turn a financial capability on.
    """

    if direct_trade_enabled():
        return COMMERCE_MODE_DIRECT_TRADE
    if matchmaking_enabled():
        return COMMERCE_MODE_MATCHMAKING
    return COMMERCE_MODE_HISTORY_ONLY


def payment_enabled() -> bool:
    """Effective collection capability, including provider readiness."""

    if not direct_trade_enabled():
        return False
    try:
        from app.services.payment_gateway import provider_configured

        return provider_configured() is True
    except Exception:
        return False


def recharge_enabled() -> bool:
    return payment_enabled()


def withdrawal_enabled() -> bool:
    if not direct_trade_enabled():
        return False
    try:
        return sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED) is True
    except Exception:
        return False


def platform_capabilities() -> dict:
    return {
        "commerce_mode": commerce_mode(),
        "matchmaking_enabled": matchmaking_enabled(),
        "credential_escrow_enabled": credential_escrow_enabled(),
        "direct_trade_enabled": direct_trade_enabled(),
        "payment_enabled": payment_enabled(),
        "recharge_enabled": recharge_enabled(),
        "withdraw_enabled": withdrawal_enabled(),
        "history_read_enabled": True,
    }


def require_matchmaking_enabled() -> None:
    if not matchmaking_enabled():
        raise BizError(MATCHMAKING_DISABLED_MESSAGE, status_code=409)


def require_direct_trade_enabled() -> None:
    """Fail closed at every server-side transaction commitment boundary."""

    if not direct_trade_enabled():
        raise BizError(INQUIRY_ONLY_MESSAGE, status_code=409)


def require_recharge_enabled() -> None:
    if not recharge_enabled():
        raise BizError(RECHARGE_DISABLED_MESSAGE, status_code=503)


def require_withdrawal_enabled() -> None:
    if not withdrawal_enabled():
        raise BizError(WITHDRAWAL_DISABLED_MESSAGE, status_code=503)
