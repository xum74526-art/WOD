"""Scheduled official OHLC synchronization.

Only this worker performs network I/O. Public market handlers read the durable
resolution-aware candle table and continue serving the last successful batch
when the provider is temporarily unavailable.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from threading import Lock
from typing import Any

from sqlalchemy import func

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.kai_pricing import KaiPricingError, get_aggregated_candles
from app.models.market_price import MarketCandleSyncStatus, MarketPriceCandle, MarketPriceSnapshot
from app.services.gpu_catalog import canonicalize_gpu, normalize_gpu_variant
from app.services.market_sync import utcnow


SOURCE = "kai"
CANDLE_RANGE_INTERVALS = {
    # One seven-day hourly backfill also supplies the trailing 24-hour view.
    # Keeping one job per persisted resolution avoids duplicate refresh clocks
    # competing for the same v2 uniqueness key.
    "7d": 60 * 60,
    "30d": 4 * 60 * 60,
    "90d": 24 * 60 * 60,
}
CANDLE_RANGE_REFRESH_SECONDS = {
    "7d": 10 * 60,
    "30d": 60 * 60,
    "90d": 6 * 60 * 60,
}
_SYNC_LOCK = Lock()
_DISPATCH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="market-candle-agent")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _status(db) -> MarketCandleSyncStatus:
    row = db.query(MarketCandleSyncStatus).filter(MarketCandleSyncStatus.source == SOURCE).one_or_none()
    if row is None:
        row = MarketCandleSyncStatus(
            source=SOURCE,
            refresh_seconds=max(int(settings.MARKET_CANDLE_SYNC_SECONDS), 60),
        )
        db.add(row)
        db.flush()
    return row


def _due(db, force: bool) -> bool:
    row = _status(db)
    if not row.enabled:
        return False
    if force or row.last_attempt_at is None:
        return True
    return utcnow() - row.last_attempt_at >= timedelta(seconds=max(row.refresh_seconds, 60))


def _identities() -> list[tuple[str, str]]:
    db = SessionLocal()
    try:
        rows = db.query(
            MarketPriceSnapshot.gpu_model,
            MarketPriceSnapshot.gpu_variant,
        ).filter(
            MarketPriceSnapshot.source == SOURCE,
            MarketPriceSnapshot.billing_mode == "ondemand",
        ).distinct().all()
        identities = {
            (
                canonicalize_gpu(model) or model,
                normalize_gpu_variant(canonicalize_gpu(model) or model, variant),
            )
            for model, variant in rows if model
        }
        # KAI_RANKING_MAX_PRODUCTS limits one live ranking request; it must not
        # become a permanent allow-list for historical K lines.  Returning the
        # full identity set lets the bounded job selector below rotate fairly
        # across every GPU exposed by /api/market/models.
        return sorted(identities)
    finally:
        db.close()


def _fetch(
    identity: tuple[str, str],
    range_name: str,
) -> tuple[tuple[str, str], str, int, dict[str, Any]]:
    model, variant = identity
    payload = dict(get_aggregated_candles(model, variant, range_name))
    try:
        interval_seconds = int(payload.get("bucket_seconds"))
    except (TypeError, ValueError) as exc:
        raise KaiPricingError("upstream_invalid_response") from exc
    if (
        payload.get("range") != range_name
        or interval_seconds != CANDLE_RANGE_INTERVALS[range_name]
    ):
        raise KaiPricingError("upstream_invalid_response")
    return identity, range_name, interval_seconds, payload


def _pending_jobs(
    identities: list[tuple[str, str]],
    force: bool,
) -> list[tuple[tuple[str, str], str]]:
    jobs = [
        (identity, range_name)
        for identity in identities
        for range_name in CANDLE_RANGE_INTERVALS
    ]
    if force:
        return jobs

    db = SessionLocal()
    try:
        rows = db.query(
            MarketPriceCandle.gpu_model,
            MarketPriceCandle.gpu_variant,
            MarketPriceCandle.interval_seconds,
            func.max(MarketPriceCandle.collected_at),
        ).filter(
            MarketPriceCandle.source == SOURCE,
            MarketPriceCandle.billing_mode == "ondemand",
        ).group_by(
            MarketPriceCandle.gpu_model,
            MarketPriceCandle.gpu_variant,
            MarketPriceCandle.interval_seconds,
        ).all()
    finally:
        db.close()
    latest = {
        (model, variant, int(interval_seconds)): collected_at
        for model, variant, interval_seconds, collected_at in rows
        if collected_at is not None
    }
    now = utcnow()
    due_jobs = [
        (identity, range_name)
        for identity, range_name in jobs
        if (
            latest.get((*identity, CANDLE_RANGE_INTERVALS[range_name])) is None
            or now - latest[(*identity, CANDLE_RANGE_INTERVALS[range_name])]
            >= timedelta(seconds=CANDLE_RANGE_REFRESH_SECONDS[range_name])
        )
    ]
    # Missing and oldest histories go first.  The previous implementation
    # sliced the alphabetically sorted identity list, so models after the first
    # 24 could never obtain official history.  A bounded rotating job queue
    # protects the upstream while guaranteeing eventual coverage for all.
    range_priority = {"7d": 0, "30d": 1, "90d": 2}
    due_jobs.sort(key=lambda item: (
        latest.get((*item[0], CANDLE_RANGE_INTERVALS[item[1]])) is not None,
        latest.get((*item[0], CANDLE_RANGE_INTERVALS[item[1]])) or datetime.min,
        range_priority.get(item[1], 99),
        item[0],
    ))
    return due_jobs[:max(int(settings.MARKET_CANDLE_SYNC_MAX_JOBS), 1)]


def _signature(payload: dict[str, Any]) -> str:
    stable = {
        key: value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, Decimal) else value
        for key, value in payload.items()
        if key not in {
            "collected_at",
            "updated_at",
            # These describe the containing live publication, not a candle's
            # OHLC content. Including them rewrote the full history window on
            # every live refresh even when every historical value was equal.
            "source_observed_at",
            "source_version",
        }
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _store_payloads(
    payloads: list[tuple[tuple[str, str], str, int, dict[str, Any]]],
) -> tuple[int, int]:
    db = SessionLocal()
    inserted = 0
    accepted = 0
    collected_at = utcnow()
    try:
        for (model, variant), _range_name, interval_seconds, payload in payloads:
            provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
            source_observed_at = _parse_datetime(provenance.get("as_of"))
            history_as_of = _parse_datetime(provenance.get("history_as_of"))
            source_version = str(provenance.get("data_version") or "").strip() or None
            method = str(payload.get("method") or "official_ohlc").strip()[:96]
            data_quality = str(payload.get("data_quality") or "official").strip()[:32]
            if source_observed_at is not None and source_observed_at > collected_at:
                continue
            closed_through = min(
                item for item in (source_observed_at, history_as_of, collected_at)
                if item is not None
            )
            prepared: dict[datetime, dict[str, Any]] = {}
            for candle in payload.get("candles") or []:
                if not isinstance(candle, dict):
                    continue
                start_time = _parse_datetime(candle.get("start_time"))
                end_time = _parse_datetime(candle.get("end_time"))
                prices = {
                    "open_price_cny": _decimal(candle.get("open_price_cny")),
                    "high_price_cny": _decimal(candle.get("high_price_cny")),
                    "low_price_cny": _decimal(candle.get("low_price_cny")),
                    "close_price_cny": _decimal(candle.get("close_price_cny")),
                }
                if (
                    start_time is None
                    or end_time is None
                    or end_time - start_time != timedelta(seconds=interval_seconds)
                    or end_time > closed_through
                    or any(value is None for value in prices.values())
                ):
                    continue
                low = prices["low_price_cny"]
                high = prices["high_price_cny"]
                open_price = prices["open_price_cny"]
                close_price = prices["close_price_cny"]
                if low > min(open_price, close_price) or high < max(open_price, close_price) or high < low:
                    continue
                values = {
                    "source": SOURCE,
                    "gpu_model": model,
                    "gpu_variant": variant,
                    "billing_mode": "ondemand",
                    "interval_seconds": interval_seconds,
                    "start_time": start_time,
                    "end_time": end_time,
                    **prices,
                    "sample_count": max(int(candle.get("sample_count") or 0), 0),
                    "observation_count": max(int(candle.get("observation_count") or 0), 0),
                    "method": method,
                    "data_quality": data_quality,
                    "source_version": source_version,
                    "source_observed_at": source_observed_at,
                }
                prepared[start_time] = values
            if not prepared:
                continue

            starts = sorted(prepared)
            existing_rows = db.query(MarketPriceCandle).filter(
                MarketPriceCandle.source == SOURCE,
                MarketPriceCandle.gpu_model == model,
                MarketPriceCandle.gpu_variant == variant,
                MarketPriceCandle.billing_mode == "ondemand",
                MarketPriceCandle.interval_seconds == interval_seconds,
                MarketPriceCandle.start_time >= starts[0],
                MarketPriceCandle.start_time <= starts[-1],
            ).all()
            existing = {row.start_time: row for row in existing_rows}
            changed = False
            latest_unchanged = None
            for start_time in starts:
                values = prepared[start_time]
                signature = _signature(values)
                current = existing.get(start_time)
                accepted += 1
                if current is not None and current.signature == signature:
                    if latest_unchanged is None or current.start_time > latest_unchanged.start_time:
                        latest_unchanged = current
                    continue
                changed = True
                if current is None:
                    db.add(MarketPriceCandle(**values, signature=signature, collected_at=collected_at))
                    inserted += 1
                else:
                    for field, value in values.items():
                        setattr(current, field, value)
                    current.signature = signature
                    current.collected_at = collected_at
                    current.updated_at = collected_at
            if not changed and latest_unchanged is not None:
                # One bounded heartbeat advances the due clock. Older equal
                # rows keep their original timestamps and are not rewritten.
                latest_unchanged.collected_at = collected_at
        cutoff = utcnow() - timedelta(days=max(int(settings.MARKET_CANDLE_HISTORY_DAYS), 1))
        db.query(MarketPriceCandle).filter(MarketPriceCandle.end_time < cutoff).delete()
        db.commit()
        return inserted, accepted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, KaiPricingError):
        return exc.code
    return "sync_failed"


def sync_market_candles(force: bool = False) -> dict[str, Any]:
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "already_running", "source": SOURCE}
    try:
        db = SessionLocal()
        try:
            if not _due(db, force):
                return {"status": "not_due", "source": SOURCE}
            state = _status(db)
            state.last_attempt_at = utcnow()
            state.refresh_seconds = max(int(settings.MARKET_CANDLE_SYNC_SECONDS), 60)
            db.commit()
        finally:
            db.close()

        identities = _identities()
        if not identities:
            raise RuntimeError("no_market_models")
        payloads: list[tuple[tuple[str, str], str, int, dict[str, Any]]] = []
        errors: list[str] = []
        jobs = _pending_jobs(identities, force)
        if not jobs:
            return {"status": "not_due", "source": SOURCE}
        with ThreadPoolExecutor(max_workers=min(2, len(jobs)), thread_name_prefix="kai-candle-fetch") as executor:
            futures = {
                executor.submit(_fetch, identity, range_name): (identity, range_name)
                for identity, range_name in jobs
            }
            for future in as_completed(futures):
                try:
                    identity, range_name, interval_seconds, payload = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(_error_code(exc))
                    continue
                if payload.get("candles"):
                    payloads.append((identity, range_name, interval_seconds, payload))
                else:
                    errors.append("empty_history")
        if not payloads:
            raise RuntimeError(errors[0] if errors else "empty_history")

        inserted, accepted = _store_payloads(payloads)
        db = SessionLocal()
        try:
            state = _status(db)
            state.status = "ok" if not errors else "partial"
            state.model_count = len({identity for identity, _range, _interval, _payload in payloads})
            state.candle_count = accepted
            state.last_success_at = utcnow()
            state.last_error = errors[0] if errors else None
            db.commit()
        finally:
            db.close()
        return {
            "status": "ok" if not errors else "partial",
            "source": SOURCE,
            "models": len({identity for identity, _range, _interval, _payload in payloads}),
            "ranges": len(payloads),
            "candles": accepted,
            "inserted": inserted,
        }
    except Exception as exc:  # noqa: BLE001
        db = SessionLocal()
        try:
            state = _status(db)
            state.status = "error"
            state.last_error = _error_code(exc)
            db.commit()
        finally:
            db.close()
        return {"status": "error", "source": SOURCE, "error_code": _error_code(exc)}
    finally:
        _SYNC_LOCK.release()


def dispatch_market_candle_sync() -> str:
    _DISPATCH_EXECUTOR.submit(sync_market_candles, False)
    return SOURCE
