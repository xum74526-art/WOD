"""Reward-program mode, startup safety and ledger naming.

The in-app reward mode credits nonwithdrawable card-hours only. It is deliberately
separate from the future live settlement switch so historical synthetic
reward rows never become spendable merely because the in-app program is enabled.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


REWARD_MODE_DISABLED = "disabled"
REWARD_MODE_CLOSED_TEST = "test_card_hours"
REWARD_MODE_LIVE = "live"

PROGRAM_CONSUMER = "consumer_purchase"
PROGRAM_SUPPLIER = "supplier_sales"
PROGRAM_INVITE = "invite_first_order"
PROGRAM_INVITE_QUALIFICATION = "invite_qualification_bonus"
PROGRAM_INVITE_COMMISSION = "invite_consumption_commission"

_LIVE_LEDGER_TYPES = {
    "consumer": "rebate",
    "supplier": "supplier_rebate",
    "invite": "invite_reward",
}

_TEST_LEDGER_TYPES = {
    "consumer": "test_rebate",
    "supplier": "test_supplier",
    "invite": "test_invite",
}

_PROGRAM_LEDGER_TYPES = {
    PROGRAM_CONSUMER: "consumer_purchase_rebate",
    PROGRAM_SUPPLIER: "supplier_sales_rebate",
    PROGRAM_INVITE: "invite_first_order_reward",
    PROGRAM_INVITE_QUALIFICATION: "invite_qualification_bonus",
    PROGRAM_INVITE_COMMISSION: "invite_consumption_commission",
}

_PROGRAM_PUBLIC_TYPES = {
    PROGRAM_CONSUMER: "rebate",
    PROGRAM_SUPPLIER: "supplier_rebate",
    PROGRAM_INVITE: "invite_reward",
    PROGRAM_INVITE_QUALIFICATION: "invite_reward",
    PROGRAM_INVITE_COMMISSION: "invite_reward",
}


def program_enabled(program_code: str) -> bool:
    switches = {
        PROGRAM_CONSUMER: settings.CONSUMER_REWARD_ENABLED,
        PROGRAM_SUPPLIER: settings.SUPPLIER_REWARD_ENABLED,
        PROGRAM_INVITE: settings.INVITE_REWARD_ENABLED,
        PROGRAM_INVITE_QUALIFICATION: settings.INVITE_V2_ENABLED,
        PROGRAM_INVITE_COMMISSION: settings.INVITE_V2_ENABLED,
    }
    if program_code not in switches:
        raise ValueError(f"unsupported reward program: {program_code}")
    return bool(switches[program_code])


def any_reward_program_enabled() -> bool:
    return any(program_enabled(program) for program in _PROGRAM_LEDGER_TYPES)


def assert_reward_configuration_safe() -> None:
    """Reject mixed legacy/new writers before the API starts.

    Legacy rewards use asset flags and non-versioned ledger references, while
    the current programs use immutable accrual rows. Running both writers would
    make one confirmed order eligible in two accounting systems.
    """
    legacy_enabled = bool(
        settings.REWARD_SERVICE_ENABLED or settings.CLOSED_TEST_REWARD_ENABLED
    )
    if legacy_enabled:
        raise RuntimeError(
            "legacy reward writers are retired; enable only versioned reward programs"
        )
    if settings.INVITE_REWARD_ENABLED and settings.INVITE_V2_ENABLED:
        raise RuntimeError(
            "invite V1 and V2 writers cannot be enabled together"
        )
    try:
        ZoneInfo(settings.REWARD_TIMEZONE)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"invalid REWARD_TIMEZONE: {settings.REWARD_TIMEZONE}"
        ) from exc


def program_ledger_type(program_code: str) -> str:
    try:
        return _PROGRAM_LEDGER_TYPES[program_code]
    except KeyError as exc:
        raise ValueError(f"unsupported reward program: {program_code}") from exc


def reward_mode() -> str:
    if settings.REWARD_SERVICE_ENABLED:
        return REWARD_MODE_LIVE
    if settings.CLOSED_TEST_REWARD_ENABLED:
        return REWARD_MODE_CLOSED_TEST
    return REWARD_MODE_DISABLED


def reward_program_enabled() -> bool:
    return reward_mode() != REWARD_MODE_DISABLED


def reward_ledger_type(kind: str) -> str:
    mode = reward_mode()
    if kind not in _LIVE_LEDGER_TYPES:
        raise ValueError(f"unsupported reward kind: {kind}")
    if mode == REWARD_MODE_CLOSED_TEST:
        return _TEST_LEDGER_TYPES[kind]
    return _LIVE_LEDGER_TYPES[kind]


def active_reward_ledger_types(kind: str) -> tuple[str, ...]:
    if not reward_program_enabled():
        return ()
    return (reward_ledger_type(kind),)


def ledger_filter_types(public_type: str) -> tuple[str, ...] | None:
    """Map the stable public filter to live and legacy in-app ledger rows."""
    for kind, live_type in _LIVE_LEDGER_TYPES.items():
        if public_type == live_type:
            new_types = tuple(
                ledger_type
                for program, ledger_type in _PROGRAM_LEDGER_TYPES.items()
                if _PROGRAM_PUBLIC_TYPES[program] == public_type
            )
            return (live_type, _TEST_LEDGER_TYPES[kind], *new_types)
    return None


def is_test_reward_type(ledger_type: str) -> bool:
    return ledger_type in _TEST_LEDGER_TYPES.values()


def public_reward_type(ledger_type: str) -> str:
    for program, program_type in _PROGRAM_LEDGER_TYPES.items():
        if ledger_type == program_type:
            return _PROGRAM_PUBLIC_TYPES[program]
    for kind, test_type in _TEST_LEDGER_TYPES.items():
        if ledger_type == test_type:
            return _LIVE_LEDGER_TYPES[kind]
    return ledger_type
