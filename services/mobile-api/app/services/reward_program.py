"""Reward-program mode and ledger naming.

The closed-test mode credits *test card-hours* only.  It is deliberately
separate from the future live settlement switch so historical synthetic
reward rows never become spendable merely because the closed test is enabled.
"""

from app.core.config import settings


REWARD_MODE_DISABLED = "disabled"
REWARD_MODE_CLOSED_TEST = "test_card_hours"
REWARD_MODE_LIVE = "live"

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
    """Map the stable public filter to live and closed-test ledger rows."""
    for kind, live_type in _LIVE_LEDGER_TYPES.items():
        if public_type == live_type:
            return live_type, _TEST_LEDGER_TYPES[kind]
    return None


def is_test_reward_type(ledger_type: str) -> bool:
    return ledger_type in _TEST_LEDGER_TYPES.values()


def public_reward_type(ledger_type: str) -> str:
    for kind, test_type in _TEST_LEDGER_TYPES.items():
        if ledger_type == test_type:
            return _LIVE_LEDGER_TYPES[kind]
    return ledger_type
