from __future__ import annotations

from datetime import datetime

from app.models.market_price import MarketSourceStatus


CURRENT_SOURCE_STATES = {"live", "delayed"}
HOT_SOURCE_STATES = {"live"}


def source_state(item: MarketSourceStatus, now: datetime) -> str:
    """Classify source freshness without exposing provider error details."""
    if item.status == "error" and not item.last_success_at:
        return "unavailable"
    if not item.last_success_at:
        return item.status or "pending"
    age = max((now - item.last_success_at).total_seconds(), 0)
    live_limit = max(item.refresh_seconds * 2, 30)
    # A failed latest attempt must never be called live.  A still-recent last
    # success is delayed, then becomes stale/unavailable as it ages.
    if item.status == "error":
        if age <= max(live_limit * 2, 120):
            return "delayed"
        if age <= 600:
            return "stale"
        return "unavailable"
    if age <= live_limit:
        return "live" if item.status in ("ok", "empty") else item.status
    if age <= max(live_limit * 2, 120):
        return "delayed"
    if age <= 600:
        return "stale"
    return "unavailable"


def product_market_source(product) -> str:
    explicit = str(getattr(product, "market_source", "") or "").strip().lower()
    if explicit:
        return explicit
    # Compatibility for databases that have not yet run init_db.  Startup
    # persists this inference; runtime decisions then use the explicit field.
    if product.source_price is None:
        return "wod"
    if str(product.source_currency or "").upper() == "USD":
        return "vast"
    return "autodl"


def product_market_state(
    product,
    source_states: dict[str, str],
    now: datetime,
    max_age_seconds: int,
) -> str:
    source = product_market_source(product)
    if source == "wod":
        return "live"
    state = source_states.get(source, "unavailable")
    if state != "live":
        return state
    if not product.price_updated_at:
        return "stale"
    observed_at = product.price_updated_at.replace(tzinfo=None)
    age = max((now - observed_at).total_seconds(), 0)
    return "live" if age <= max(max_age_seconds, 60) else "stale"
