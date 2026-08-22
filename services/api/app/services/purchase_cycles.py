"""Shared purchase-cycle policy for compute products and orders."""

PURCHASE_CYCLE_DAYS = (1, 7, 30, 90, 180, 365)


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
