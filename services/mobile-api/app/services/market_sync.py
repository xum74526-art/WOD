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

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.market_price import MarketPriceSnapshot, MarketSourceStatus
from app.models.product import Product
from app.services.gpu_catalog import (
    canonicalize_gpu,
    memory_variant_from_text,
    normalize_gpu_variant,
)


_SYNC_LOCK = Lock()
_FX_LOCK = Lock()
_FX_CACHE: dict[str, Any] = {}
_SOURCE_LOCKS = {source: Lock() for source in ("wod", "vast", "autodl")}
_MARKET_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="market-source")

SOURCE_INTERVALS = {
    "wod": settings.WOD_MARKET_REFRESH_SECONDS,
    "vast": settings.VAST_MARKET_REFRESH_SECONDS,
    "autodl": settings.AUTODL_MARKET_REFRESH_SECONDS,
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


def get_usd_cny_rate() -> tuple[Decimal, str, str]:
    now = utcnow()
    with _FX_LOCK:
        cached_at = _FX_CACHE.get("fetched_at")
        if cached_at and now - cached_at < timedelta(seconds=settings.FX_REFRESH_SECONDS):
            return _FX_CACHE["rate"], _FX_CACHE["source"], _FX_CACHE["date"]
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(settings.FX_API_URL)
            response.raise_for_status()
            payload = response.json()
        rate = Decimal(str(payload["rate"]))
        if rate <= 0:
            raise ValueError("invalid USD/CNY reference rate")
        result = {
            "rate": rate,
            "source": "ECB via Frankfurter",
            "date": str(payload.get("date") or ""),
            "fetched_at": now,
        }
        _FX_CACHE.clear()
        _FX_CACHE.update(result)
        return rate, result["source"], result["date"]


def _collect_wod(db: Session) -> list[dict[str, Any]]:
    products = db.query(Product).filter(
        Product.status == "on",
        Product.stock > 0,
        Product.supplier_id.isnot(None),
        Product.source_price.is_(None),
    ).all()
    rows = []
    for product in products:
        model = canonicalize_gpu(product.gpu_model) or canonicalize_gpu(product.name)
        price = Decimal(str(product.price or 0))
        if not model or price <= 0:
            continue
        rows.append({
            "gpu_model": model,
            "gpu_variant": normalize_gpu_variant(model, memory_variant_from_text(product.memory)),
            "price": price,
            "currency": "CNY",
            "billing_mode": "wod_listing",
            "available": max(int(product.stock or 0), 0),
        })
    return rows


def _collect_autodl() -> list[dict[str, Any]]:
    if not settings.AUTODL_TOKEN:
        raise RuntimeError("missing AUTODL_TOKEN")
    headers = {"Authorization": settings.AUTODL_TOKEN, "Content-Type": "application/json"}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.post(
            f"{settings.AUTODL_API_BASE_URL.rstrip('/')}/api/v1/machine/list",
            headers=headers,
            json={"page_index": 1, "page_size": 500, "charge_type": "payg"},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != "Success":
        raise RuntimeError(str(payload.get("msg") or payload.get("code") or "AutoDL request failed"))
    rows = []
    for offer in payload.get("data", {}).get("list", []):
        model = canonicalize_gpu(offer.get("gpu_name"))
        idle = int(offer.get("gpu_idle_num") or 0)
        price = Decimal(str(offer.get("payg_price") or 0)) / Decimal("1000")
        if not model or idle <= 0 or price <= 0:
            continue
        memory_bytes = Decimal(str(offer.get("gpu_memory") or 0))
        memory_gb = memory_bytes / Decimal(1024 ** 3) if memory_bytes > 0 else Decimal("0")
        rows.append({
            "gpu_model": model,
            "gpu_variant": normalize_gpu_variant(model, float(memory_gb)),
            "price": price,
            "currency": "CNY",
            "billing_mode": "ondemand",
            "available": idle,
        })
    return rows


def _collect_vast() -> list[dict[str, Any]]:
    if not settings.VAST_API_KEY:
        raise RuntimeError("missing VAST_API_KEY")
    headers = {"Authorization": f"Bearer {settings.VAST_API_KEY}", "Content-Type": "application/json"}
    body = {
        "limit": 500,
        "type": "ondemand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
    }
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.post(
            f"{settings.VAST_API_BASE_URL.rstrip('/')}/bundles",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    rows = []
    for offer in payload.get("offers", []):
        model = canonicalize_gpu(offer.get("gpu_name"))
        gpu_count = int(offer.get("num_gpus") or 0)
        total_price = Decimal(str(offer.get("dph_total") or 0))
        if not model or gpu_count <= 0 or total_price <= 0:
            continue
        memory_mb = Decimal(str(offer.get("gpu_ram") or 0))
        rows.append({
            "gpu_model": model,
            "gpu_variant": normalize_gpu_variant(
                model,
                float(memory_mb / Decimal(1024)) if memory_mb > 0 else None,
            ),
            "price": total_price / Decimal(gpu_count),
            "currency": "USD",
            "billing_mode": "ondemand",
            "available": gpu_count,
        })
    return rows


def _signature(payload: dict[str, Any]) -> str:
    serializable = {key: str(value) if isinstance(value, Decimal) else value for key, value in payload.items()}
    return hashlib.sha256(json.dumps(serializable, sort_keys=True).encode("utf-8")).hexdigest()


def _aggregate_and_store(db: Session, source: str, rows: list[dict[str, Any]], observed_at: datetime) -> tuple[int, int]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["gpu_model"], row["gpu_variant"], row["billing_mode"], row["currency"])].append(row)

    fx_rate: Decimal | None = None
    fx_source: str | None = None
    fx_date: str | None = None
    if any(key[3] == "USD" for key in grouped):
        fx_rate, fx_source, fx_date = get_usd_cny_rate()

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
        group_fx = Decimal("1") if currency == "CNY" else fx_rate
        group_fx_source = "CNY native" if currency == "CNY" else fx_source
        group_fx_date = observed_at.date().isoformat() if currency == "CNY" else fx_date
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
    message = str(exc).lower()
    if "missing" in message and ("token" in message or "api_key" in message or "credential" in message):
        return "credentials_missing"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return "authentication_failed"
        if status == 429:
            return "rate_limited"
    if isinstance(exc, httpx.TimeoutException):
        return "upstream_timeout"
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

        if source == "wod":
            rows = _collect_wod(db)
        elif source == "vast":
            rows = _collect_vast()
        elif source == "autodl":
            rows = _collect_autodl()
        else:
            raise ValueError(f"unknown source: {source}")

        inserted, samples = _aggregate_and_store(db, source, rows, now)
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
        return [_sync_source(source, force) for source in ("wod", "vast", "autodl")]
    finally:
        _SYNC_LOCK.release()


def dispatch_market_sync() -> list[str]:
    """Schedule independent collectors and return immediately to the scheduler."""
    scheduled = []
    for source in ("wod", "vast", "autodl"):
        _MARKET_EXECUTOR.submit(_sync_source, source, False)
        scheduled.append(source)
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
