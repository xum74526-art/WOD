"""Collect and aggregate source-attributed GPU prices without simulated data."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.kai_pricing import KaiPricingError, fetch_price_batch, normalized_current_quotes
from app.models.market_price import MarketPriceSnapshot, MarketSourceStatus


_SYNC_LOCK = Lock()
_SOURCE_LOCKS = {"kai": Lock()}
_MARKET_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="market-kai")

SOURCE_INTERVALS = {
    "kai": settings.KAI_PRICING_REFRESH_SECONDS,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _percentile(values: list[Decimal], ratio: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _without_outliers(values: list[Decimal]) -> list[Decimal]:
    if len(values) < 4:
        return values
    q1 = _percentile(values, Decimal("0.25"))
    q3 = _percentile(values, Decimal("0.75"))
    iqr = q3 - q1
    lower = q1 - iqr * Decimal("1.5")
    upper = q3 + iqr * Decimal("1.5")
    filtered = [value for value in values if lower <= value <= upper]
    return filtered or values


def _collect_kai() -> tuple[list[dict[str, Any]], datetime]:
    """Collect KAI's current cross-section using its own publication time.

    ``gpuCountOptions`` is intentionally not copied to ``available``: it is a
    configuration limit, not a live inventory count.
    """

    batch = fetch_price_batch()
    rows = [{
        "gpu_model": item["gpu_model"],
        "gpu_variant": item["gpu_variant"],
        "price": item["price_cny"],
        "currency": "CNY",
        "billing_mode": "ondemand",
        "available": 0,
    } for item in normalized_current_quotes(batch)]
    return rows, batch.observed_at


def _signature(payload: dict[str, Any]) -> str:
    serializable = {key: str(value) if isinstance(value, Decimal) else value for key, value in payload.items()}
    return hashlib.sha256(json.dumps(serializable, sort_keys=True).encode("utf-8")).hexdigest()


def _aggregate_and_store(db: Session, source: str, rows: list[dict[str, Any]], observed_at: datetime) -> tuple[int, int]:
    if source != "kai":
        raise ValueError("market_source_retired")
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["gpu_model"], row["gpu_variant"], row["billing_mode"], row["currency"])].append(row)

    inserted = 0
    accepted_samples = 0
    for (model, variant, billing_mode, currency), offers in grouped.items():
        raw_values = [Decimal(str(item["price"])) for item in offers if Decimal(str(item["price"])) > 0]
        values = _without_outliers(raw_values)
        if not values:
            continue
        accepted_samples += len(values)
        min_price = min(values)
        p25_price = _percentile(values, Decimal("0.25"))
        median_price = _percentile(values, Decimal("0.5"))
        p75_price = _percentile(values, Decimal("0.75"))
        max_price = max(values)
        if currency != "CNY":
            # KAI publishes native CNY. Rejecting another currency prevents a
            # retired provider row from being reintroduced through this path.
            continue
        group_fx = Decimal("1")
        group_fx_source = "CNY native"
        group_fx_date = observed_at.date().isoformat()
        payload = {
            "source": source,
            "gpu_model": model,
            "gpu_variant": variant,
            "billing_mode": billing_mode,
            "currency": currency,
            "min_price": min_price.quantize(Decimal("0.000001")),
            "p25_price": p25_price.quantize(Decimal("0.000001")),
            "median_price": median_price.quantize(Decimal("0.000001")),
            "p75_price": p75_price.quantize(Decimal("0.000001")),
            "max_price": max_price.quantize(Decimal("0.000001")),
            "sample_count": len(values),
            "available_gpu_count": sum(max(int(item.get("available") or 0), 0) for item in offers),
            "fx_rate": group_fx,
        }
        signature = _signature(payload)
        latest = db.query(MarketPriceSnapshot).filter(
            MarketPriceSnapshot.source == source,
            MarketPriceSnapshot.gpu_model == model,
            MarketPriceSnapshot.gpu_variant == variant,
            MarketPriceSnapshot.billing_mode == billing_mode,
        ).order_by(MarketPriceSnapshot.observed_at.desc()).first()
        # Keep storage bounded during 10-second checks, but persist a periodic
        # observation even when the price is unchanged.  Otherwise a genuinely
        # stable market would never gain a second calendar day and would remain
        # "insufficient history" forever.
        unchanged_gap = timedelta(seconds=max(settings.MARKET_UNCHANGED_SNAPSHOT_SECONDS, 60))
        if latest and latest.signature == signature and observed_at - latest.observed_at < unchanged_gap:
            continue
        cny = group_fx if group_fx and group_fx > 0 else None
        db.add(MarketPriceSnapshot(
            **payload,
            min_price_cny=(min_price * cny).quantize(Decimal("0.000001")) if cny else None,
            median_price_cny=(median_price * cny).quantize(Decimal("0.000001")) if cny else None,
            max_price_cny=(max_price * cny).quantize(Decimal("0.000001")) if cny else None,
            fx_source=group_fx_source,
            fx_date=group_fx_date,
            data_quality="verified" if len(values) >= 3 else "limited_sample",
            signature=signature,
            observed_at=observed_at,
            fetched_at=utcnow(),
        ))
        inserted += 1
    return inserted, accepted_samples


def _status(db: Session, source: str) -> MarketSourceStatus:
    item = db.query(MarketSourceStatus).filter(MarketSourceStatus.source == source).first()
    if not item:
        item = MarketSourceStatus(source=source, refresh_seconds=SOURCE_INTERVALS[source])
        db.add(item)
        db.flush()
    return item


def _sync_error_code(exc: Exception) -> str:
    if isinstance(exc, KaiPricingError):
        return exc.code
    message = str(exc).lower()
    if "missing" in message and ("token" in message or "api_key" in message or "credential" in message):
        return "credentials_missing"
    return "upstream_error"


def _source_due(db: Session, source: str, force: bool) -> bool:
    if force:
        return True
    item = _status(db, source)
    if not item.last_attempt_at:
        return True
    return utcnow() - item.last_attempt_at >= timedelta(seconds=SOURCE_INTERVALS[source])


def _sync_source(source: str, force: bool) -> dict[str, Any]:
    source_lock = _SOURCE_LOCKS[source]
    if not source_lock.acquire(blocking=False):
        return {"source": source, "skipped": True, "reason": "already_running"}
    db = SessionLocal()
    now = utcnow()
    try:
        if not _source_due(db, source, force):
            return {"source": source, "skipped": True}
        state = _status(db, source)
        state.last_attempt_at = now
        state.refresh_seconds = SOURCE_INTERVALS[source]
        state.enabled = True
        db.commit()

        observed_at = now
        if source == "kai":
            rows, observed_at = _collect_kai()
        else:
            raise ValueError(f"unknown source: {source}")

        inserted, samples = _aggregate_and_store(db, source, rows, observed_at)
        state = _status(db, source)
        state.status = "ok" if samples else "empty"
        state.sample_count = samples
        state.last_success_at = now
        state.last_error = None
        db.commit()
        return {"source": source, "inserted": inserted, "samples": samples}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        error_code = _sync_error_code(exc)
        state = _status(db, source)
        state.status = "error"
        # Store and return only a stable error category.  Provider response
        # bodies, request details, and credentials must not reach DB records,
        # API responses, scheduler return values, or logs.
        state.last_error = error_code
        state.last_attempt_at = now
        db.commit()
        return {"source": source, "error_code": error_code}
    finally:
        db.close()
        source_lock.release()


def sync_market(force: bool = False) -> list[dict[str, Any]]:
    if not _SYNC_LOCK.acquire(blocking=False):
        return [{"status": "already_running"}]
    try:
        return [_sync_source("kai", force)]
    finally:
        _SYNC_LOCK.release()


def dispatch_market_sync() -> list[str]:
    """Schedule independent collectors and return immediately to the scheduler."""
    scheduled = []
    _MARKET_EXECUTOR.submit(_sync_source, "kai", False)
    scheduled.append("kai")
    return scheduled


def cleanup_market_history() -> int:
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=max(settings.MARKET_HISTORY_DAYS, 1))
        count = db.query(MarketPriceSnapshot).filter(MarketPriceSnapshot.observed_at < cutoff).delete()
        db.commit()
        return count
    finally:
        db.close()
