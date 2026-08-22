from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Condition
import time
from types import SimpleNamespace
from typing import Callable, Iterable, TypeVar

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.market_price import MarketPriceSnapshot, MarketSourceStatus
from app.services.gpu_catalog import canonicalize_gpu, gpu_variant_aliases, normalize_gpu_variant
from app.services.market_freshness import CURRENT_SOURCE_STATES, HOT_SOURCE_STATES, source_state as _source_state
from app.services.market_sync import _without_outliers, utcnow
from app.services.market_history_sync import (
    HistorySelection,
    history_source_status,
    select_market_history,
    select_market_history_bulk,
)
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/market", tags=["market"])
SOURCE_NAMES = {"wod": "WOD", "vast": "Vast.ai", "autodl": "AutoDL"}
# A rolling seven-day change needs real observations at both ends of a window.
# Two endpoint dates spanning six full days are published as sparse/limited;
# seven distinct observed UTC dates are required for verified/full coverage.
# Adjacent or single observations never become a fabricated seven-day value.
MIN_RANGE_DAYS = 7
MIN_RANGE_SPAN_HOURS = 6 * 24
RANGE_REPRESENTATIVE_SECONDS = 60 * 60

_Payload = TypeVar("_Payload")


class _MarketResponseCache:
    """Small process-local TTL cache with per-key request coalescing.

    FastAPI creates a DB session before entering a route, but SQLAlchemy does
    not check out a connection until the first query. Waiting duplicate calls
    therefore consume no SQLite pool connections while one request computes
    the shared real-data result.
    """

    def __init__(self, max_entries: int = 256):
        self.max_entries = max_entries
        self._condition = Condition()
        self._entries: dict[tuple, tuple[float, object]] = {}
        self._inflight: set[tuple] = set()

    def get_or_load(self, key: tuple, ttl_seconds: float, loader: Callable[[], _Payload]) -> _Payload:
        while True:
            now = time.monotonic()
            with self._condition:
                cached = self._entries.get(key)
                if cached and cached[0] > now:
                    return cached[1]  # type: ignore[return-value]
                if key not in self._inflight:
                    self._inflight.add(key)
                    break
                self._condition.wait(timeout=1.0)
        try:
            value = loader()
        except Exception:
            with self._condition:
                self._inflight.discard(key)
                self._condition.notify_all()
            raise
        with self._condition:
            if len(self._entries) >= self.max_entries:
                expired = [entry_key for entry_key, entry in self._entries.items() if entry[0] <= time.monotonic()]
                for entry_key in expired:
                    self._entries.pop(entry_key, None)
                if len(self._entries) >= self.max_entries:
                    oldest = min(self._entries, key=lambda entry_key: self._entries[entry_key][0])
                    self._entries.pop(oldest, None)
            self._entries[key] = (time.monotonic() + max(ttl_seconds, 0.1), value)
            self._inflight.discard(key)
            self._condition.notify_all()
        return value

    def clear(self) -> None:
        with self._condition:
            self._entries.clear()
            self._condition.notify_all()


_MARKET_RESPONSE_CACHE = _MarketResponseCache()


def _cache_allowed(db: Session) -> bool:
    """Do not let isolated in-memory test databases share process cache data."""
    database = db.get_bind().url.database
    return database not in {None, "", ":memory:"}


def _cached_payload(
    db: Session,
    key: tuple,
    ttl_seconds: float,
    loader: Callable[[], _Payload],
) -> _Payload:
    return _MARKET_RESPONSE_CACHE.get_or_load(key, ttl_seconds, loader) if _cache_allowed(db) else loader()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def _public_error_code(message: str | None) -> str | None:
    if not message:
        return None
    normalized = message.lower()
    if normalized in {
        "credentials_missing",
        "authentication_failed",
        "rate_limited",
        "upstream_timeout",
        "upstream_error",
        "history_credentials_missing",
        "history_credentials_missing_permission",
        "history_rate_limited",
        "history_upstream_timeout",
        "history_upstream_error",
        "history_invalid_response",
        "history_empty_or_missing_vram",
    }:
        return normalized
    if "missing" in normalized and ("token" in normalized or "api_key" in normalized or "credential" in normalized):
        return "credentials_missing"
    if "401" in normalized or "403" in normalized or "unauthorized" in normalized or "forbidden" in normalized:
        return "authentication_failed"
    if "429" in normalized or "rate limit" in normalized:
        return "rate_limited"
    if "timeout" in normalized or "timed out" in normalized:
        return "upstream_timeout"
    return "upstream_error"


def _latest_rows(db: Session) -> list[MarketPriceSnapshot]:
    latest_times = db.query(
        MarketPriceSnapshot.source.label("source"),
        MarketPriceSnapshot.gpu_model.label("gpu_model"),
        MarketPriceSnapshot.gpu_variant.label("gpu_variant"),
        MarketPriceSnapshot.billing_mode.label("billing_mode"),
        func.max(MarketPriceSnapshot.observed_at).label("observed_at"),
    ).group_by(
        MarketPriceSnapshot.source,
        MarketPriceSnapshot.gpu_model,
        MarketPriceSnapshot.gpu_variant,
        MarketPriceSnapshot.billing_mode,
    ).subquery()
    return db.query(MarketPriceSnapshot).join(
        latest_times,
        and_(
            MarketPriceSnapshot.source == latest_times.c.source,
            MarketPriceSnapshot.gpu_model == latest_times.c.gpu_model,
            MarketPriceSnapshot.gpu_variant == latest_times.c.gpu_variant,
            MarketPriceSnapshot.billing_mode == latest_times.c.billing_mode,
            MarketPriceSnapshot.observed_at == latest_times.c.observed_at,
        ),
    ).all()


def _normalized_snapshot_identity(row: MarketPriceSnapshot) -> tuple[str, str]:
    model = canonicalize_gpu(row.gpu_model) or row.gpu_model
    return model, normalize_gpu_variant(model, row.gpu_variant)


def _latest_normalized_rows(
    rows: Iterable[MarketPriceSnapshot],
) -> list[tuple[str, str, MarketPriceSnapshot]]:
    """Collapse documented aliases while keeping provider/billing contracts separate."""
    latest: dict[tuple[str, str, str, str], MarketPriceSnapshot] = {}
    for row in rows:
        model, variant = _normalized_snapshot_identity(row)
        key = (model, variant, row.source, row.billing_mode)
        current = latest.get(key)
        if current is None or row.observed_at > current.observed_at:
            latest[key] = row
    return [(model, variant, row) for (model, variant, _, _), row in latest.items()]


def _snapshot_out(row: MarketPriceSnapshot, checked_at: datetime | None = None) -> dict:
    model, variant = _normalized_snapshot_identity(row)
    return {
        "source": row.source,
        "source_name": SOURCE_NAMES.get(row.source, row.source),
        "gpu_model": model,
        "gpu_variant": variant,
        "billing_mode": row.billing_mode,
        "currency": row.currency,
        "min_price": float(row.min_price),
        "p25_price": float(row.p25_price),
        "median_price": float(row.median_price),
        "p75_price": float(row.p75_price),
        "max_price": float(row.max_price),
        "min_price_cny": float(row.min_price_cny) if row.min_price_cny is not None else None,
        "median_price_cny": float(row.median_price_cny) if row.median_price_cny is not None else None,
        "max_price_cny": float(row.max_price_cny) if row.max_price_cny is not None else None,
        "sample_count": row.sample_count,
        "available_gpu_count": row.available_gpu_count,
        "fx_rate": float(row.fx_rate) if row.fx_rate is not None else None,
        "fx_source": row.fx_source,
        "fx_date": row.fx_date,
        "data_quality": row.data_quality,
        "observed_at": _iso(row.observed_at),
        "source_checked_at": _iso(checked_at),
    }


def _weighted_median(rows: list[MarketPriceSnapshot]) -> float | None:
    priced = sorted(
        [(Decimal(row.median_price_cny), max(row.sample_count, 1)) for row in rows if row.median_price_cny is not None],
        key=lambda item: item[0],
    )
    if not priced:
        return None
    total = sum(weight for _, weight in priced)
    cursor = 0
    for price, weight in priced:
        cursor += weight
        if cursor * 2 >= total:
            return float(price)
    return float(priced[-1][0])


def _weighted_median_values(values: Iterable[tuple[Decimal, int]]) -> Decimal | None:
    """Return a weighted median without fabricating values between observations."""
    priced = sorted(
        [(Decimal(price), max(int(weight), 1)) for price, weight in values],
        key=lambda item: item[0],
    )
    if not priced:
        return None
    total = sum(weight for _, weight in priced)
    cursor = 0
    for price, weight in priced:
        cursor += weight
        if cursor * 2 >= total:
            return price
    return priced[-1][0]


def _bucket_time(value: datetime, seconds: int) -> datetime:
    """Floor a UTC-naive database timestamp to a deterministic UTC bucket."""
    epoch = datetime(1970, 1, 1)
    offset = int((value - epoch).total_seconds())
    return epoch + timedelta(seconds=(offset // seconds) * seconds)


def _build_market_candles(rows: Iterable, candle_seconds: int, tick_seconds: int) -> list[dict]:
    """Aggregate the observed market index into OHLC candles.

    Each tick is a sample-count weighted median of quotes actually observed in
    that time slot. High and low are the highest and lowest index observations
    inside the candle, not the cross-sectional maximum and minimum asking price
    from unrelated sellers. Missing slots are deliberately omitted; no
    interpolation or synthetic movement is introduced.
    """
    # First reduce each exact source series inside a time slot.  This prevents a
    # source that happened to refresh many times in one slot from overpowering
    # another source, while preserving sample-count weighting between the
    # source representatives themselves.
    tick_source_rows: dict[tuple[datetime, str], list] = defaultdict(list)
    for row in rows:
        if row.median_price_cny is None:
            continue
        tick_source_rows[(_bucket_time(row.observed_at, tick_seconds), row.source)].append(row)

    tick_rows: dict[datetime, list[dict]] = defaultdict(list)
    for (tick_time, source), observed in tick_source_rows.items():
        values = _without_outliers([Decimal(row.median_price_cny) for row in observed])
        if not values:
            continue
        tick_rows[tick_time].append({
            "source": source,
            "price": _median(values),
            "sample_count": max(sum(max(int(row.sample_count), 0) for row in observed), 1),
            "observation_count": len(observed),
        })

    ticks: list[dict] = []
    for tick_time, observed in sorted(tick_rows.items()):
        price = _weighted_median_values(
            (row["price"], row["sample_count"]) for row in observed
        )
        if price is None:
            continue
        ticks.append({
            "time": tick_time,
            "price": price,
            "sample_count": sum(row["sample_count"] for row in observed),
            "observation_count": sum(row["observation_count"] for row in observed),
            "sources": {row["source"] for row in observed},
        })

    grouped: dict[datetime, list[dict]] = defaultdict(list)
    for tick in ticks:
        grouped[_bucket_time(tick["time"], candle_seconds)].append(tick)

    candles: list[dict] = []
    for start_time, candle_ticks in sorted(grouped.items()):
        candle_ticks.sort(key=lambda item: item["time"])
        prices = [item["price"] for item in candle_ticks]
        candles.append({
            "start_time": _iso(start_time),
            "end_time": _iso(start_time + timedelta(seconds=candle_seconds)),
            "open_price_cny": float(prices[0]),
            "high_price_cny": float(max(prices)),
            "low_price_cny": float(min(prices)),
            "close_price_cny": float(prices[-1]),
            "sample_count": sum(item["sample_count"] for item in candle_ticks),
            "observation_count": sum(item["observation_count"] for item in candle_ticks),
            "sources": sorted({source for item in candle_ticks for source in item["sources"]}),
        })
    return candles


def _range_volatility(values: list[Decimal]) -> float:
    """Observed price range as a percentage of the source median."""
    priced = sorted(value for value in values if value > 0)
    if len(priced) < 2:
        return 0.0
    midpoint = len(priced) // 2
    median = (
        (priced[midpoint - 1] + priced[midpoint]) / Decimal("2")
        if len(priced) % 2 == 0
        else priced[midpoint]
    )
    if median <= 0:
        return 0.0
    return round(float((priced[-1] - priced[0]) / median * Decimal("100")), 2)


def _median(values: Iterable[Decimal]) -> Decimal:
    priced = sorted(values)
    if not priced:
        return Decimal("0")
    midpoint = len(priced) // 2
    return (
        (priced[midpoint - 1] + priced[midpoint]) / Decimal("2")
        if len(priced) % 2 == 0
        else priced[midpoint]
    )


def _source_range_metric(points: list[tuple[datetime, Decimal]]) -> dict:
    """Build a robust range from daily medians of one exact source/contract series.

    Intraday offer-pool churn must not be presented as seven-day movement. A
    value is published only after at least two UTC dates and 24 hours of actual
    coverage. IQR filtering is applied inside each day and again across daily
    medians; observed values are never replaced or simulated.
    """
    # Snapshot rows are event-driven: a changing offer pool can persist dozens
    # of rows while an unchanged price is stored only periodically.  Counting
    # raw rows directly would therefore weight "busy" periods more heavily.
    # Reduce every fixed UTC hour to one robust representative before deriving
    # daily medians.
    by_hour: dict[datetime, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for observed_at, value in points:
        if value is not None and value > 0:
            by_hour[_bucket_time(observed_at, RANGE_REPRESENTATIVE_SECONDS)].append(
                (observed_at, Decimal(value))
            )

    hourly: list[tuple[datetime, Decimal, datetime, datetime, int]] = []
    for hour, values in by_hour.items():
        clean_values = _without_outliers([value for _, value in values])
        hourly.append((
            hour,
            _median(clean_values),
            min(observed_at for observed_at, _ in values),
            max(observed_at for observed_at, _ in values),
            len(values),
        ))

    by_day: dict[date, list[tuple[datetime, Decimal, datetime, datetime, int]]] = defaultdict(list)
    for item in hourly:
        by_day[item[0].date()].append(item)

    daily: list[tuple[date, Decimal, datetime, datetime, int]] = []
    for observed_day, values in by_day.items():
        clean_values = _without_outliers([item[1] for item in values])
        daily.append((
            observed_day,
            _median(clean_values),
            min(item[2] for item in values),
            max(item[3] for item in values),
            sum(item[4] for item in values),
        ))
    daily.sort(key=lambda item: item[0])

    accepted_values = _without_outliers([item[1] for item in daily])
    accepted_counts = Counter(accepted_values)
    accepted_daily = []
    for item in daily:
        if accepted_counts[item[1]] > 0:
            accepted_daily.append(item)
            accepted_counts[item[1]] -= 1

    day_count = len(accepted_daily)
    point_count = sum(item[4] for item in accepted_daily)
    span_hours = 0.0
    if accepted_daily:
        span_hours = max(
            (max(item[3] for item in accepted_daily) - min(item[2] for item in accepted_daily)).total_seconds() / 3600,
            0.0,
        )
    # Two real endpoint dates spanning six days support a seven-day change even
    # when the collector missed intermediate days. Seven distinct dates remain
    # the threshold for calling the coverage complete/verified.
    enough_history = day_count >= 2 and span_hours >= MIN_RANGE_SPAN_HOURS
    value = _range_volatility([item[1] for item in accepted_daily]) if enough_history else None
    daily_values = [item[1] for item in accepted_daily]
    change = None
    if enough_history and daily_values and daily_values[0] > 0:
        change = round(float((daily_values[-1] / daily_values[0] - Decimal("1")) * Decimal("100")), 2)
    coverage_status = (
        "complete"
        if enough_history and day_count >= MIN_RANGE_DAYS
        else "sparse_window"
        if enough_history
        else "partial"
        if day_count >= 2
        else "point_only"
        if day_count == 1
        else "unavailable"
    )
    return {
        "volatility_7d": value,
        "volatility_status": "available" if enough_history else "insufficient_history",
        "volatility_quality": "verified" if enough_history and day_count >= MIN_RANGE_DAYS else "limited_sample",
        "history_day_count": day_count,
        "history_point_count": point_count,
        "history_span_hours": round(span_hours, 1),
        "history_bucket_count": len(hourly),
        "history_coverage_status": coverage_status,
        "change_7d_pct": change,
        "range_low_cny": float(min(daily_values)) if enough_history and daily_values else None,
        "range_high_cny": float(max(daily_values)) if enough_history and daily_values else None,
        "flat_price_observed": bool(enough_history and daily_values and min(daily_values) == max(daily_values)),
    }


def _seven_day_metrics(
    db: Session,
    now: datetime,
    allowed_sources: set[str] | None = None,
) -> dict[tuple[str, str], dict]:
    # The history table grows continuously.  Loading complete ORM entities here
    # also deserializes every price percentile, FX field and quality column even
    # though the seven-day calculation needs only six values.  On the closed-
    # test SQLite database that made /models and /ranking take several seconds.
    # Select the exact source-series identity and observed median only; the
    # calculation and its truthfulness rules remain unchanged.
    rows = db.query(
        MarketPriceSnapshot.gpu_model,
        MarketPriceSnapshot.gpu_variant,
        MarketPriceSnapshot.billing_mode,
        MarketPriceSnapshot.source,
        MarketPriceSnapshot.observed_at,
        MarketPriceSnapshot.median_price_cny,
    ).filter(
        MarketPriceSnapshot.observed_at >= now - timedelta(days=7),
        MarketPriceSnapshot.median_price_cny.isnot(None),
        MarketPriceSnapshot.median_price_cny > 0,
    )
    if allowed_sources is not None:
        rows = rows.filter(MarketPriceSnapshot.source.in_(allowed_sources))

    exact_series: dict[tuple[str, str, str, str], list[tuple[datetime, Decimal]]] = defaultdict(list)
    for row in rows.order_by(MarketPriceSnapshot.observed_at.asc()).all():
        model = canonicalize_gpu(row.gpu_model) or row.gpu_model
        variant = normalize_gpu_variant(model, row.gpu_variant)
        exact_series[(model, variant, row.billing_mode, row.source)].append(
            (row.observed_at, Decimal(row.median_price_cny))
        )

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for (model, variant, billing_mode, source), points in exact_series.items():
        metric = _source_range_metric(points)
        grouped[(model, variant, billing_mode)].append({
            **metric,
            "source": source,
            "billing_mode": billing_mode,
        })

    mode_results: dict[tuple[str, str], list[dict]] = defaultdict(list)
    source_priority = {"vast": 0, "autodl": 1, "wod": 2}
    for (model, variant, billing_mode), source_metrics in grouped.items():
        # Keep each provider's price population independent. Pick the strongest
        # observed series instead of taking a median of provider volatilities.
        source_metrics.sort(key=lambda item: (
            item["volatility_7d"] is None,
            item["volatility_quality"] != "verified",
            -item["history_span_hours"],
            -item["history_day_count"],
            source_priority.get(item["source"], 9),
        ))
        selected = source_metrics[0]
        mode_results[(model, variant)].append({
            **selected,
            "volatility_source_count": 1 if selected["volatility_7d"] is not None else 0,
            "volatility_sources": [selected["source"]] if selected["volatility_7d"] is not None else [],
            "volatility_billing_mode": billing_mode,
            "volatility_method": "single_source_hourly_robust_median_daily_range",
        })

    # A model can exist under incompatible charging contracts.  Never blend
    # those contracts into one percentage.  Ranking represents on-demand cloud
    # supply when available, otherwise the first contract with sufficient
    # history (and finally the best-covered insufficient candidate).
    billing_priority = {"ondemand": 0, "wod_listing": 1}
    result: dict[tuple[str, str], dict] = {}
    for key, candidates in mode_results.items():
        candidates.sort(key=lambda item: (
            item["volatility_7d"] is None,
            billing_priority.get(item["volatility_billing_mode"], 9),
            -item["history_span_hours"],
            -item["history_day_count"],
        ))
        result[key] = candidates[0]
    return result


def _empty_metric() -> dict:
    return {
        "volatility_7d": None,
        "volatility_status": "insufficient_history",
        "volatility_quality": "limited_sample",
        "history_day_count": 0,
        "history_point_count": 0,
        "history_span_hours": 0.0,
        "history_min_daily_sample_count": 0,
        "history_bucket_count": 0,
        "history_coverage_status": "unavailable",
        "volatility_source_count": 0,
        "volatility_sources": [],
        "volatility_billing_mode": None,
        "volatility_method": "hourly_robust_median_daily_range",
        "change_7d_pct": None,
        "range_low_cny": None,
        "range_high_cny": None,
        "history_provenance": None,
        "flat_price_observed": False,
    }


def _historical_metric(
    db: Session,
    now: datetime,
    model: str,
    variant: str,
) -> dict | None:
    """Return a real temporal change/range, preferring official history.

    The current live quote is deliberately not spliced into an archived index:
    Vast's live offer search and the historical archive have different listing
    populations. Combining them created a false last-candle jump despite every
    input price being real.
    """
    selected = select_market_history(db, model, variant, now - timedelta(days=7), now)
    return _historical_metric_from_selection(selected)


def _historical_metric_from_selection(selected: HistorySelection | None) -> dict | None:
    """Convert one already-selected, source-attributed series to public metrics."""
    if selected is None:
        return None
    if not selected.available or not selected.points:
        # An attributed external series exists, but it does not yet meet the
        # seven-day/cross-listing quality gate. Return an explicit non-hot
        # metric so callers do not fall back to a noisy live-snapshot range.
        metric = _empty_metric()
        metric.update({
            "history_day_count": selected.day_count,
            "history_point_count": len(selected.points),
            "history_span_hours": selected.span_hours,
            "history_min_daily_sample_count": selected.min_daily_sample_count,
            "history_bucket_count": len(selected.points),
            "volatility_source_count": 1 if selected.points else 0,
            "volatility_sources": [selected.points[0].dataset_source] if selected.points else [],
            "volatility_billing_mode": "ondemand",
            "volatility_method": "earliest_to_latest_daily_index_change",
            "history_provenance": selected.provenance,
            "history_coverage_status": (
                "partial" if selected.day_count >= 2 else "single" if selected.day_count == 1 else "unavailable"
            ),
        })
        return metric
    by_day: dict[date, list[Decimal]] = defaultdict(list)
    for point in selected.points:
        if point.representative_price_cny is not None and point.representative_price_cny > 0:
            by_day[point.observed_at.date()].append(Decimal(point.representative_price_cny))
    components = [selected.points[0].dataset_source]
    daily = sorted((day, _median(_without_outliers(values))) for day, values in by_day.items())
    # ``selected.available`` already guarantees two real endpoint dates across
    # at least six days. Missing middle dates make this a sparse seven-day
    # observation, not a reason to erase the real endpoints.
    if len(daily) < 2:
        return _empty_metric()
    first, last = daily[0][1], daily[-1][1]
    if first <= 0:
        return _empty_metric()
    change = round(float((last / first - Decimal("1")) * Decimal("100")), 2)
    values = [value for _, value in daily]
    earliest_at = selected.points[0].observed_at
    latest_at = selected.points[-1].observed_at
    span_hours = max((latest_at - earliest_at).total_seconds() / 3600, 0.0)
    provenance = dict(selected.provenance or {})
    provenance["components"] = components
    provenance["live_component_included"] = False
    return {
        # Compatibility only: older clients sort this field. Its method is now
        # explicitly earliest-to-latest absolute change, not a high/low range.
        "volatility_7d": abs(change),
        "volatility_status": "available",
        "volatility_quality": provenance.get("coverage_quality", "limited_sample"),
        "history_day_count": len(daily),
        "history_point_count": len(selected.points),
        "history_span_hours": round(span_hours, 1),
        "history_min_daily_sample_count": selected.min_daily_sample_count,
        "history_bucket_count": len(selected.points),
        "volatility_source_count": len(components),
        "volatility_sources": components,
        "volatility_billing_mode": "ondemand",
        "volatility_method": "earliest_to_latest_daily_index_change",
        "change_7d_pct": change,
        "range_low_cny": float(min(values)),
        "range_high_cny": float(max(values)),
        "history_provenance": provenance,
        "history_coverage_status": (
            "complete" if len(daily) >= MIN_RANGE_DAYS else "sparse_window"
        ),
        "flat_price_observed": min(values) == max(values),
    }


def _historical_metrics(
    db: Session,
    now: datetime,
    identities: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], dict]:
    """Resolve all ranking/model history in one query instead of N+1 scans."""
    selected = select_market_history_bulk(
        db,
        identities,
        now - timedelta(days=7),
        now,
    )
    return {
        identity: metric
        for identity, selection in selected.items()
        if (metric := _historical_metric_from_selection(selection)) is not None
    }


def _history_metric_matches_live_sources(metric: dict | None, live_sources: Iterable[str]) -> bool:
    """Only attach an archive to a currently comparable provider.

    A GPU model/VRAM match is not enough: AutoDL, Vast, AWS and RunPod use
    different listing populations and pricing contracts.  Treating (for
    example) a Vast RTX4090D archive as AutoDL history produced a mathematically
    real but commercially false seven-day change.
    """
    if not metric:
        return False
    provenance = metric.get("history_provenance") or {}
    provider = str(provenance.get("upstream_provider") or "").strip().lower()
    aliases = {
        "vast.ai": "vast",
        "vastai": "vast",
        "auto dl": "autodl",
        "auto_dl": "autodl",
    }
    provider = aliases.get(provider, provider)
    comparable = {aliases.get(str(source).strip().lower(), str(source).strip().lower()) for source in live_sources}
    return bool(provider and provider in comparable)


def _source_states(db: Session, now: datetime) -> dict[str, str]:
    return {row.source: _source_state(row, now) for row in db.query(MarketSourceStatus).all() if row.enabled}


def _current_sources(db: Session, now: datetime) -> set[str]:
    return {source for source, state in _source_states(db, now).items() if state in CURRENT_SOURCE_STATES}


def _comparison_rows(db: Session, now: datetime, allowed_sources: set[str]) -> list[MarketPriceSnapshot]:
    since = now - timedelta(hours=30)
    until = now - timedelta(hours=24)
    comparison_times = db.query(
        MarketPriceSnapshot.source.label("source"),
        MarketPriceSnapshot.gpu_model.label("gpu_model"),
        MarketPriceSnapshot.gpu_variant.label("gpu_variant"),
        MarketPriceSnapshot.billing_mode.label("billing_mode"),
        func.max(MarketPriceSnapshot.observed_at).label("observed_at"),
    ).filter(
        MarketPriceSnapshot.observed_at >= since,
        MarketPriceSnapshot.observed_at <= until,
        MarketPriceSnapshot.source.in_(allowed_sources),
    ).group_by(
        MarketPriceSnapshot.source,
        MarketPriceSnapshot.gpu_model,
        MarketPriceSnapshot.gpu_variant,
        MarketPriceSnapshot.billing_mode,
    ).subquery()
    return db.query(MarketPriceSnapshot).join(
        comparison_times,
        and_(
            MarketPriceSnapshot.source == comparison_times.c.source,
            MarketPriceSnapshot.gpu_model == comparison_times.c.gpu_model,
            MarketPriceSnapshot.gpu_variant == comparison_times.c.gpu_variant,
            MarketPriceSnapshot.billing_mode == comparison_times.c.billing_mode,
            MarketPriceSnapshot.observed_at == comparison_times.c.observed_at,
        ),
    ).all()


def _pick_variant(rows: list[MarketPriceSnapshot], model: str) -> str:
    counts: dict[str, int] = defaultdict(int)
    canonical_model = canonicalize_gpu(model) or model
    for row in rows:
        row_model, row_variant = _normalized_snapshot_identity(row)
        if row_model == canonical_model:
            counts[row_variant] += row.sample_count
    return max(counts, key=counts.get) if counts else ""


@router.get("/sources/status")
def source_status(db: Session = Depends(get_db)):
    now = utcnow()
    rows = db.query(MarketSourceStatus).order_by(MarketSourceStatus.source.asc()).all()
    return success({
        "server_time": _iso(now),
        "items": [{
            "source": row.source,
            "source_name": SOURCE_NAMES.get(row.source, row.source),
            "enabled": row.enabled,
            "status": _source_state(row, now),
            "raw_status": row.status,
            "refresh_seconds": row.refresh_seconds,
            "sample_count": row.sample_count,
            "last_attempt_at": _iso(row.last_attempt_at),
            "last_success_at": _iso(row.last_success_at),
            "has_error": bool(row.last_error),
            "error_code": _public_error_code(row.last_error),
        } for row in rows],
        "history_items": history_source_status(db),
    })


@router.get("/models")
def models(db: Session = Depends(get_db)):
    return success(_cached_payload(db, ("market_models",), 30, lambda: _models_payload(db)))


def _models_payload(db: Session) -> dict:
    now = utcnow()
    source_states = _source_states(db, now)
    current_sources = {source for source, state in source_states.items() if state in HOT_SOURCE_STATES}
    rows = _latest_normalized_rows(row for row in _latest_rows(db) if row.source in current_sources)
    metrics = _seven_day_metrics(db, now, current_sources)
    grouped: dict[tuple[str, str], dict] = {}
    for model, variant, row in rows:
        key = (model, variant)
        item = grouped.setdefault(key, {
            "gpu_model": model,
            "gpu_variant": variant,
            "sources": [],
            "sample_count": 0,
            "available_gpu_count": 0,
        })
        if row.source not in item["sources"]:
            item["sources"].append(row.source)
        item["sample_count"] += row.sample_count
        item["available_gpu_count"] += row.available_gpu_count
    historical = _historical_metrics(db, now, grouped.keys())
    for key, item in grouped.items():
        archived = historical.get(key)
        if not _history_metric_matches_live_sources(archived, item["sources"]):
            archived = None
        item.update(archived or metrics.get(key, _empty_metric()))
        states = [source_states.get(source, "pending") for source in item["sources"]]
        item["market_status"] = "live" if states and all(state == "live" for state in states) else "delayed"
    items = sorted(grouped.values(), key=lambda item: (
        item["volatility_7d"] is None,
        -(item["volatility_7d"] or 0),
        -item["sample_count"],
        item["gpu_model"],
        item["gpu_variant"],
    ))
    return {
        "server_time": _iso(now),
        "items": items,
        "source_states": source_states,
    }


@router.get("/prices/latest")
def latest_prices(
    model: str,
    variant: str | None = None,
    sources: str = "vast,autodl",
    db: Session = Depends(get_db),
):
    now = utcnow()
    allowed_sources = {part.strip() for part in sources.split(",") if part.strip() in SOURCE_NAMES}
    source_states = _source_states(db, now)
    current_sources = {source for source in allowed_sources if source_states.get(source) in CURRENT_SOURCE_STATES}
    all_latest = _latest_rows(db)
    canonical_model = canonicalize_gpu(model) or model
    selected_variant = normalize_gpu_variant(
        canonical_model,
        variant if variant is not None else _pick_variant(all_latest, canonical_model),
    )
    rows = [
        row for row_model, row_variant, row in _latest_normalized_rows(all_latest)
        if row_model == canonical_model and row_variant == selected_variant and row.source in current_sources
    ]
    statuses = {row.source: row for row in db.query(MarketSourceStatus).all()}
    items = [_snapshot_out(row, statuses.get(row.source).last_success_at if statuses.get(row.source) else None) for row in rows]
    cny_mins = [float(row.min_price_cny) for row in rows if row.min_price_cny is not None]
    cny_maxes = [float(row.max_price_cny) for row in rows if row.max_price_cny is not None]
    return success({
        "server_time": _iso(now),
        "next_refresh_in": 10,
        "gpu_model": canonical_model,
        "gpu_variant": selected_variant,
        "summary": {
            "median_price_cny": _weighted_median(rows),
            "min_price_cny": min(cny_mins) if cny_mins else None,
            "max_price_cny": max(cny_maxes) if cny_maxes else None,
            "sample_count": sum(row.sample_count for row in rows),
            "available_gpu_count": sum(row.available_gpu_count for row in rows),
            "source_count": len(rows),
        },
        "items": items,
        "requested_source_states": {source: source_states.get(source, "pending") for source in sorted(allowed_sources)},
        "excluded_sources": sorted(allowed_sources - current_sources),
    })


@router.get("/prices/history")
def price_history(
    model: str,
    variant: str | None = None,
    range: str = "24h",  # noqa: A002
    sources: str = "vast,autodl",
    db: Session = Depends(get_db),
):
    ranges = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    if range not in ranges:
        raise BizError("不支持的时间范围")
    allowed_sources = {part.strip() for part in sources.split(",") if part.strip() in SOURCE_NAMES}
    all_latest = _latest_rows(db)
    canonical_model = canonicalize_gpu(model) or model
    selected_variant = normalize_gpu_variant(
        canonical_model,
        variant if variant is not None else _pick_variant(all_latest, canonical_model),
    )
    variant_filters = gpu_variant_aliases(canonical_model, selected_variant)
    since = utcnow() - ranges[range]
    # Keep chart payload generation lightweight on SQLite: only fields exposed
    # by this endpoint are fetched from the continuously growing history table.
    rows = db.query(
        MarketPriceSnapshot.source,
        MarketPriceSnapshot.observed_at,
        MarketPriceSnapshot.median_price_cny,
        MarketPriceSnapshot.median_price,
        MarketPriceSnapshot.currency,
        MarketPriceSnapshot.sample_count,
        MarketPriceSnapshot.data_quality,
    ).filter(
        MarketPriceSnapshot.gpu_model == canonical_model,
        MarketPriceSnapshot.gpu_variant.in_(variant_filters),
        MarketPriceSnapshot.observed_at >= since,
        MarketPriceSnapshot.source.in_(allowed_sources),
    ).order_by(MarketPriceSnapshot.observed_at.asc()).all()
    grouped: dict[str, list[dict]] = defaultdict(list)
    source_times: dict[str, list[datetime]] = defaultdict(list)
    source_states = _source_states(db, utcnow())
    for row in rows:
        source_times[row.source].append(row.observed_at)
        grouped[row.source].append({
            "time": _iso(row.observed_at),
            "price_cny": float(row.median_price_cny) if row.median_price_cny is not None else None,
            "price_original": float(row.median_price),
            "currency": row.currency,
            "sample_count": row.sample_count,
            "data_quality": row.data_quality,
        })
    return success({
        "server_time": _iso(utcnow()),
        "gpu_model": canonical_model,
        "gpu_variant": selected_variant,
        "range": range,
        "series": [{
            "source": source,
            "source_name": SOURCE_NAMES[source],
            "source_status": source_states.get(source, "pending"),
            "curve_status": (
                "full"
                if len({item.date() for item in source_times[source]}) >= MIN_RANGE_DAYS
                and (max(source_times[source]) - min(source_times[source])).total_seconds() / 3600 >= MIN_RANGE_SPAN_HOURS
                else "partial"
                if len(points) >= 2
                else "single"
            ),
            "coverage_day_count": len({item.date() for item in source_times[source]}),
            "coverage_span_hours": round(
                (max(source_times[source]) - min(source_times[source])).total_seconds() / 3600,
                1,
            ),
            "points": points,
        } for source, points in grouped.items()],
    })


@router.get("/prices/candles")
def price_candles(
    model: str,
    variant: str | None = None,
    range: str = "24h",  # noqa: A002
    sources: str = "vast,autodl",
    billing_mode: str = "ondemand",
    db: Session = Depends(get_db),
):
    normalized_sources = tuple(sorted({
        part.strip() for part in sources.split(",") if part.strip() in SOURCE_NAMES
    }))
    cache_key = (
        "market_candles", model, variant or "", range, normalized_sources, billing_mode,
    )
    ttl_seconds = 300 if range in {"7d", "30d"} else 30 if range == "24h" else 8
    payload = _cached_payload(
        db,
        cache_key,
        ttl_seconds,
        lambda: _price_candles_payload(model, variant, range, sources, billing_mode, db),
    )
    return success(payload)


def _price_candles_payload(
    model: str,
    variant: str | None,
    range: str,  # noqa: A002
    sources: str,
    billing_mode: str,
    db: Session,
) -> dict:
    """Return observed OHLC candles for the selected GPU market.

    Candles use real stored source medians only. A missing time bucket remains
    missing instead of being filled with a generated line segment.
    """
    configs = {
        "1h": (timedelta(hours=1), 5 * 60, 60),
        "6h": (timedelta(hours=6), 15 * 60, 5 * 60),
        "24h": (timedelta(hours=24), 60 * 60, 15 * 60),
        # Seven-day history is presented as a daily K-line.  The licensed
        # archive is sampled roughly twice per day, so six-hour candles often
        # contained a single observation and collapsed into grey doji marks.
        # Daily buckets preserve the real first/high/low/last observations and
        # produce truthful red/green OHLC bodies without inventing movement.
        "7d": (timedelta(days=7), 24 * 60 * 60, 60 * 60),
        "30d": (timedelta(days=30), 24 * 60 * 60, 4 * 60 * 60),
    }
    if range not in configs:
        raise BizError("不支持的时间范围")
    allowed_sources = {part.strip() for part in sources.split(",") if part.strip() in SOURCE_NAMES}
    if not allowed_sources:
        raise BizError("请选择有效的数据来源")
    duration, candle_seconds, tick_seconds = configs[range]
    canonical_model = canonicalize_gpu(model) or model
    picked_variant = variant if variant is not None else _pick_variant(_latest_rows(db), canonical_model)
    selected_variant = normalize_gpu_variant(canonical_model, picked_variant)
    variant_filters = gpu_variant_aliases(canonical_model, selected_variant)
    since = utcnow() - duration
    rows = db.query(
        MarketPriceSnapshot.source,
        MarketPriceSnapshot.observed_at,
        MarketPriceSnapshot.median_price_cny,
        MarketPriceSnapshot.sample_count,
    ).filter(
        MarketPriceSnapshot.gpu_model == canonical_model,
        MarketPriceSnapshot.gpu_variant.in_(variant_filters),
        MarketPriceSnapshot.billing_mode == billing_mode,
        MarketPriceSnapshot.observed_at >= since,
        MarketPriceSnapshot.source.in_(allowed_sources),
        MarketPriceSnapshot.median_price_cny.isnot(None),
    ).order_by(MarketPriceSnapshot.observed_at.asc()).all()
    def coverage(items: list) -> tuple[int, float, int]:
        if not items:
            return (0, 0.0, 0)
        ordered = sorted(items, key=lambda item: item.observed_at)
        return (
            len({item.observed_at.date() for item in ordered}),
            max((ordered[-1].observed_at - ordered[0].observed_at).total_seconds() / 3600, 0.0),
            len(ordered),
        )

    # A request may name several acceptable providers, but a temporal series
    # must still come from one provider. Select the strongest real series and
    # expose the choice instead of blending unrelated provider price levels.
    all_live_rows = list(rows)
    rows_by_source: dict[str, list] = defaultdict(list)
    for row in all_live_rows:
        rows_by_source[row.source].append(row)
    source_priority = {"vast": 3, "autodl": 2, "wod": 1}
    selected_live_source = max(
        rows_by_source,
        key=lambda source: (
            coverage(rows_by_source[source])[0] >= MIN_RANGE_DAYS
            and coverage(rows_by_source[source])[1] >= MIN_RANGE_SPAN_HOURS,
            coverage(rows_by_source[source])[1],
            coverage(rows_by_source[source])[0],
            coverage(rows_by_source[source])[2],
            source_priority.get(source, 0),
        ),
        default=None,
    )
    live_rows = list(rows_by_source.get(selected_live_source, []))
    coverage_day_count, coverage_span_hours, _ = coverage(live_rows)
    history_status = (
        "available"
        if coverage_day_count >= 2 and coverage_span_hours >= MIN_RANGE_SPAN_HOURS
        else "partial_history"
        if len(live_rows) >= 2
        else "single_observation"
        if live_rows
        else "unavailable"
    )
    coverage_status = (
        "complete"
        if coverage_day_count >= MIN_RANGE_DAYS and coverage_span_hours >= MIN_RANGE_SPAN_HOURS
        else "sparse_window"
        if history_status == "available"
        else "partial"
        if history_status == "partial_history"
        else "single"
        if history_status == "single_observation"
        else history_status
    )
    data_quality = "direct_observation" if live_rows else None
    live_components = sorted({row.source for row in live_rows})
    provenance = ({
        "kind": "direct_observation",
        "dataset_source": "wod_market_collector",
        "upstream_provider": live_components[0] if len(live_components) == 1 else "multiple",
        "license": "provider API observations",
        "source_url": None,
        "dataset_version": None,
        "index_method": "single_source_offer_pool_median_per_gpu_hour",
        "components": live_components,
        "live_component_included": True,
        "coverage_quality": "verified" if coverage_status == "complete" else "limited_sample",
    } if live_rows else None)
    candle_rows = list(live_rows)
    latest_by_source: dict[str, object] = {}
    for row in live_rows:
        current = latest_by_source.get(row.source)
        if current is None or row.observed_at > current.observed_at:
            latest_by_source[row.source] = row
    latest_live_price = _weighted_median_values(
        (Decimal(row.median_price_cny), max(int(row.sample_count), 1))
        for row in latest_by_source.values() if row.median_price_cny is not None
    )
    latest_live_price_cny = float(latest_live_price) if latest_live_price is not None else None
    latest_live_observed_at = _iso(
        max((row.observed_at for row in latest_by_source.values()), default=None)
    )
    archive_selected = False
    # Seven-day Vast charts use one complete attributed archive. The current
    # live value is returned separately because its offer population differs
    # from the archive and is therefore not a comparable candle.
    if range == "7d" and "vast" in allowed_sources:
        selected = select_market_history(db, canonical_model, selected_variant, since, utcnow(), billing_mode)
        if selected is not None and selected.points:
            archive_rows = [SimpleNamespace(
                source=point.dataset_source,
                observed_at=point.observed_at,
                median_price_cny=point.representative_price_cny,
                sample_count=max(point.sample_count, 1),
            ) for point in selected.points]
            archive_rows.sort(key=lambda row: row.observed_at)
            archive_days, archive_span, archive_count = coverage(archive_rows)
            live_score = (
                coverage_day_count >= MIN_RANGE_DAYS and coverage_span_hours >= MIN_RANGE_SPAN_HOURS,
                len({Decimal(row.median_price_cny) for row in live_rows if row.median_price_cny is not None}) > 1,
                coverage_span_hours,
                coverage_day_count,
                len(live_rows),
            )
            archive_score = (
                selected.available,
                len({Decimal(row.median_price_cny) for row in archive_rows if row.median_price_cny is not None}) > 1,
                archive_span,
                archive_days,
                archive_count,
            )
            # Prefer a complete licensed archive. If both are partial, choose
            # the series with the broader real time coverage. Never splice the
            # two populations together merely to make a longer-looking line.
            if archive_count >= 1 and archive_score > live_score:
                archive_selected = True
                candle_rows = archive_rows
                coverage_day_count = archive_days
                coverage_span_hours = archive_span
                history_status = (
                    "available"
                    if selected.available
                    else "partial_history"
                    if archive_count >= 2
                    else "single_observation"
                )
                coverage_status = (
                    "complete"
                    if selected.available and archive_days >= MIN_RANGE_DAYS
                    else "sparse_window"
                    if selected.available
                    else "partial"
                    if archive_count >= 2
                    else "single"
                )
                provenance = dict(selected.provenance or {})
                components = [
                    f"{selected.points[0].dataset_source}:{selected.points[0].upstream_provider}"
                ] if selected.points else []
                provenance["components"] = components
                provenance["live_component_included"] = False
                data_quality = provenance.get("coverage_quality", provenance.get("kind"))
                selected_live_source = selected.points[0].upstream_provider if selected.points else selected_live_source
    candles = _build_market_candles(candle_rows, candle_seconds, tick_seconds)
    curve_status = (
        "full"
        if candles and coverage_status == "complete"
        else "partial"
        if len(candles) >= 2
        else "single"
        if len(candles) == 1
        else "unavailable"
    )
    return {
        "server_time": _iso(utcnow()),
        "gpu_model": canonical_model,
        "gpu_variant": selected_variant,
        "billing_mode": billing_mode,
        "range": range,
        "bucket_seconds": candle_seconds,
        "tick_seconds": tick_seconds,
        "method": "observed_source_robust_median_ohlc",
        "is_interpolated": False,
        "requested_sources": sorted(allowed_sources),
        "selected_source": selected_live_source,
        "history_status": history_status,
        "curve_status": curve_status,
        "coverage_class": curve_status,
        "history_coverage_status": coverage_status,
        "coverage_day_count": coverage_day_count,
        "coverage_span_hours": round(coverage_span_hours, 1),
        "data_quality": data_quality,
        "provenance": provenance,
        "latest_live_price_cny": latest_live_price_cny,
        "latest_live_observed_at": latest_live_observed_at,
        "latest_live_comparable_to_history": (
            False if archive_selected and latest_live_price_cny is not None
            else True if latest_live_price_cny is not None
            else None
        ),
        "candles": candles,
    }


@router.get("/ranking")
def ranking(db: Session = Depends(get_db)):
    # The live median refreshes frequently, while the seven-day archive does
    # not. An eight-second cache still honors the ten-second UI refresh cycle
    # and collapses simultaneous homepage/market/quote requests to one scan.
    return success(_cached_payload(db, ("market_ranking",), 8, lambda: _ranking_payload(db)))


def _ranking_payload(db: Session) -> dict:
    now = utcnow()
    source_states = _source_states(db, now)
    current_sources = {source for source, state in source_states.items() if state in HOT_SOURCE_STATES}
    latest = _latest_normalized_rows(row for row in _latest_rows(db) if row.source in current_sources)
    grouped: dict[tuple[str, str], list[MarketPriceSnapshot]] = defaultdict(list)
    for model, variant, row in latest:
        grouped[(model, variant)].append(row)
    metrics = _seven_day_metrics(db, now, current_sources)
    comparison: dict[tuple[str, str], list[MarketPriceSnapshot]] = defaultdict(list)
    for model, variant, row in _latest_normalized_rows(_comparison_rows(db, now, current_sources)):
        comparison[(model, variant)].append(row)
    historical = _historical_metrics(db, now, grouped.keys())
    items = []
    for (model, variant), rows in grouped.items():
        current = _weighted_median(rows)
        old_rows = comparison.get((model, variant), [])
        old_price = _weighted_median(old_rows)
        change = round((current / old_price - 1) * 100, 2) if current is not None and old_price else None
        archived = historical.get((model, variant))
        row_sources = [row.source for row in rows]
        if not _history_metric_matches_live_sources(archived, row_sources):
            archived = None
        metric = archived or metrics.get((model, variant), _empty_metric())
        items.append({
            "gpu_model": model,
            "gpu_variant": variant,
            "median_price_cny": current,
            "change_24h": change,
            **metric,
            "sample_count": sum(row.sample_count for row in rows),
            "available_gpu_count": sum(row.available_gpu_count for row in rows),
            "source_count": len(rows),
            "sources": [row.source for row in rows],
            "market_status": "live" if all(source_states.get(row.source) == "live" for row in rows) else "delayed",
            "hot_eligible": metric["volatility_7d"] is not None,
        })
    items.sort(key=lambda item: (
        not item["hot_eligible"],
        item["volatility_quality"] != "verified",
        -(item["volatility_7d"] or 0),
        -abs(item["change_24h"] or 0),
        -item["sample_count"],
        item["gpu_model"],
        item["gpu_variant"],
    ))
    return {"server_time": _iso(now), "items": items, "source_states": source_states}
