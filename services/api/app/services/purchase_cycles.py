"""Shared purchase-cycle policy for compute products and orders."""

PURCHASE_CYCLE_DAYS = (1, 7, 30, 90, 180, 365)
PURCHASE_HOUR_OPTIONS = (1, 6, 12, 24, 72, 168, 720)
MIN_PURCHASE_HOURS = 1
MAX_PURCHASE_HOURS = 720


def available_purchase_cycles(cycles: list | tuple | None = None) -> list[int]:
    """Return supported cycles while preserving any valid legacy custom cycles."""
    normalized = set(PURCHASE_CYCLE_DAYS)
    for value in cycles or []:
        try:
            days = int(value)
        except (TypeError, ValueError):
            continue
        if days > 0:
            normalized.add(days)
    return sorted(normalized)


def valid_purchase_hours(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_PURCHASE_HOURS <= value <= MAX_PURCHASE_HOURS
