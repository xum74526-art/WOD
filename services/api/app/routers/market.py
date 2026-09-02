from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import ceil
from statistics import median
from threading import Condition
import time
from typing import Callable, Iterable, TypeVar

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.integrations.kai_pricing import kai_http_transport_snapshot
from app.models.market_price import MarketCandleSyncStatus, MarketPriceCandle, MarketPriceSnapshot, MarketSourceStatus
from app.models.product import Product
from app.services.gpu_catalog import canonicalize_gpu, gpu_variant_aliases, normalize_gpu_variant
from app.services.market_freshness import CURRENT_SOURCE_STATES, HOT_SOURCE_STATES, source_state as _source_state
from app.services.market_sync import _without_outliers, utcnow
from app.services.market_history_sync import HistorySelection, select_market_history, select_market_history_bulk
from app.services.region_mapper import map_region
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/market", tags=["market"])
SOURCE_NAMES = {"kai": "KAI Pricing"}
# A rolling seven-day change needs real observations at both ends of a window.
# Two endpoint dates spanning six full days are published as sparse/limited;
# seven distinct observed UTC dates are required for verified/full coverage.
# Adjacent or single observations never become a fabricated seven-day value.
MIN_RANGE_DAYS = 7
MIN_RANGE_SPAN_HOURS = 6 * 24
RANGE_REPRESENTATIVE_SECONDS = 60 * 60
SEVEN_DAY_CANDLE_SECONDS = 60 * 60
MIN_SEVEN_DAY_SNAPSHOT_CANDLES = 143
RANGE_COVERAGE_RATIO = 0.85

# Public ranges share one duration contract. Candle widths get progressively
# coarser while every OHLC value still comes from observations persisted by a
# background worker. KAI's official candle API exposes 1h/4h/1d and current
# quotes have a five-minute publication window. Short ranges therefore start
# at five-minute-derived buckets; public requests never fetch or synthesize
# finer observations.
MARKET_RANGE_DURATIONS = {
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
MARKET_CANDLE_CONFIG = {
    "1h": (MARKET_RANGE_DURATIONS["1h"], 5 * 60, 5 * 60),
    "3h": (MARKET_RANGE_DURATIONS["3h"], 15 * 60, 5 * 60),
    "6h": (MARKET_RANGE_DURATIONS["6h"], 15 * 60, 5 * 60),
    "24h": (MARKET_RANGE_DURATIONS["24h"], 60 * 60, 5 * 60),
    "7d": (MARKET_RANGE_DURATIONS["7d"], SEVEN_DAY_CANDLE_SECONDS, 15 * 60),
    "30d": (MARKET_RANGE_DURATIONS["30d"], 4 * 60 * 60, 60 * 60),
    "90d": (MARKET_RANGE_DURATIONS["90d"], 24 * 60 * 60, 4 * 60 * 60),
}
MARKET_INTRADAY_BUCKET_CANDIDATES = {
    "1h": (5 * 60, 10 * 60),
    "3h": (15 * 60, 30 * 60),
    "6h": (15 * 60, 30 * 60, 60 * 60),
    # Public chart contracts must not change shape from one GPU to another.
    # Sparse real observations remain sparse one-hour candles; they are never
    # disguised as six wider two-hour candles.
    "24h": (60 * 60,),
}
STORED_CANDLE_INTERVALS = {
    "6h": 60 * 60,
    "24h": 60 * 60,
    "7d": 60 * 60,
    "30d": 4 * 60 * 60,
    "90d": 24 * 60 * 60,
}
STORED_CANDLE_INTERVAL_CANDIDATES = {
    "6h": (60 * 60,),
    "24h": (60 * 60,),
    "7d": (60 * 60,),
    "30d": (4 * 60 * 60,),
    "90d": (24 * 60 * 60,),
}

# Native one-hour and four-hour KAI histories occasionally describe materially
# different price levels for the same closed UTC window.  The public chart must
# not prefer a denser series merely because it contains more points.  Compare a
# bounded overlap and require a repeated mismatch before falling back so one
# unusual candle cannot flip the resolution. A one-percent median close drift
# is already material for a chart that presents both resolutions as one market.
RESOLUTION_REFERENCE_SECONDS = 4 * 60 * 60
RESOLUTION_COMPARISON_BUCKET_LIMIT = 42
RESOLUTION_MIN_COMPARISON_BUCKETS = 4
RESOLUTION_MEDIAN_CLOSE_DEVIATION_LIMIT = 0.01
RESOLUTION_MEDIAN_OHLC_DEVIATION_LIMIT = 0.02
RESOLUTION_LARGE_BUCKET_DEVIATION_LIMIT = 0.03
RESOLUTION_LARGE_BUCKET_RATIO_LIMIT = 0.5

# A completed official refresh can end one bucket earlier than a previous
# partial refresh. The upsert table intentionally preserves that older row, so
# the read path must not append it to the newer publication and present the two
# batches as one continuous curve. Only an isolated edge candle is quarantined,
# and only when price, source time and provenance all identify a stale batch.
OFFICIAL_EDGE_PRICE_GAP_LIMIT = 0.04
OFFICIAL_EDGE_OVERFETCH_BUCKETS = 2

# The rolling 24-hour chart is built from KAI's real five-minute current-price
# publications. A complete candidate contains 24 consecutive hourly candles,
# keeps at least 85% of the expected publication ticks and ends close to now.
# While the collector is still building that window, a recent consecutive
# suffix may be shown as partial history when every displayed hour contains at
# least half of its expected real publications. No missing tick is fabricated.
SNAPSHOT_24H_EXPECTED_CANDLES = 24
SNAPSHOT_24H_MIN_TICK_COVERAGE = 0.85
SNAPSHOT_24H_MIN_PARTIAL_TICK_COVERAGE = 0.50
SNAPSHOT_24H_MIN_PARTIAL_CANDLES = 2
SNAPSHOT_24H_MAX_LAG_SECONDS = 10 * 60

_Payload = TypeVar("_Payload")


def _card_hour_rate() -> Decimal:
    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
    if rate <= 0:
        raise BizError("卡时换算配置无效", status_code=503)
    return rate


def _to_card_hours(value: object | None) -> float | None:
    if value is None:
        return None
    return float((Decimal(str(value)) / _card_hour_rate()).quantize(Decimal("0.000001")))


def _with_card_hour_candles(payload: dict) -> dict:
    """Expose wallet-denominated prices without replacing official CNY data."""
    for candle in payload.get("candles") or []:
        if not isinstance(candle, dict):
            continue
        for name in ("open", "high", "low", "close"):
            candle[f"{name}_price_card_hours"] = _to_card_hours(
                candle.get(f"{name}_price_cny")
            )
    payload["latest_live_price_card_hours"] = _to_card_hours(
        payload.get("latest_live_price_cny")
    )
    payload["card_hour_rmb_rate"] = float(_card_hour_rate())
    payload["wallet_charge_unit"] = "CARD_HOUR"
    return payload


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


def _source_refresh_seconds(source: str) -> int | None:
    value = settings.KAI_PRICING_REFRESH_SECONDS if source == "kai" else None
    return max(int(value), 1) if value is not None else None


def _next_market_refresh_seconds(sources: Iterable[str]) -> int:
    intervals = [
        interval for source in sources
        if (interval := _source_refresh_seconds(source)) is not None
    ]
    return min(intervals) if intervals else max(int(settings.KAI_PRICING_REFRESH_SECONDS), 1)


def _kai_sources(sources: str) -> set[str]:
    requested = {part.strip().lower() for part in str(sources or "").split(",") if part.strip()}
    if requested != {"kai"}:
        raise BizError("当前行情仅支持 KAI Pricing 数据源", status_code=400)
    return {"kai"}


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
        "upstream_invalid_response",
        "upstream_response_too_large",
        "upstream_stale",
        "history_unavailable",
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
        "min_price_card_hours": _to_card_hours(row.min_price_cny),
        "median_price_card_hours": _to_card_hours(row.median_price_cny),
        "max_price_card_hours": _to_card_hours(row.max_price_cny),
        "sample_count": row.sample_count,
        "quote_sample_count": row.sample_count,
        # KAI publishes quote observations and configuration limits, not live
        # inventory.  A numeric zero would be just as misleading as a count.
        "available_gpu_count": None,
        "inventory_available": None,
        "sample_semantics": "current_quote_observations_not_inventory",
        "billing_unit": "GPU_HOUR",
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
            # One tick represents one real publication slot after duplicate
            # rows inside the same source/time bucket have been collapsed.
            "tick_count": len(candle_ticks),
            "sources": sorted({source for item in candle_ticks for source in item["sources"]}),
        })
    return candles


def _latest_contiguous_candles(candles: list[dict], candle_seconds: int) -> list[dict]:
    """Return the latest gap-free suffix of observed candles.

    A missing bucket ends the suffix instead of being hidden by joining the
    observations on either side.  This keeps the density check independent of
    interpolation and lets callers fall back to a coarser stored series.
    """
    if not candles:
        return []

    def start_time(candle: dict) -> datetime:
        value = str(candle["start_time"])
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed

    ordered = sorted(candles, key=start_time)
    contiguous = [ordered[-1]]
    expected_step = timedelta(seconds=candle_seconds)
    newer_start = start_time(ordered[-1])
    for candle in reversed(ordered[:-1]):
        older_start = start_time(candle)
        if newer_start - older_start != expected_step:
            break
        contiguous.append(candle)
        newer_start = older_start
    contiguous.reverse()
    return contiguous


def _observed_candle_density(candles: list[dict], candle_seconds: int) -> float:
    """Measure occupied buckets inside the actually observed time span."""
    if not candles:
        return 0.0
    starts = sorted(
        datetime.fromisoformat(str(item["start_time"]).replace("Z", "+00:00")).replace(tzinfo=None)
        for item in candles
    )
    possible = int((starts[-1] - starts[0]).total_seconds() // candle_seconds) + 1
    return min(len(starts) / max(possible, 1), 1.0)


def _select_observed_candle_resolution(
    rows: list,
    bucket_candidates: tuple[int, ...],
    tick_seconds: int,
) -> tuple[list[dict], int, float]:
    """Choose the finest bucket supported by real observation density.

    Candidate candles are always built from the same persisted rows. A coarser
    result combines observations but never inserts a missing observation.
    """
    evaluated: list[tuple[list[dict], int, float]] = []
    for candle_seconds in bucket_candidates:
        candles = _build_market_candles(rows, candle_seconds, min(tick_seconds, candle_seconds))
        density = _observed_candle_density(candles, candle_seconds)
        evaluated.append((candles, candle_seconds, density))
        if len(candles) < 2 or density >= RANGE_COVERAGE_RATIO:
            return candles, candle_seconds, density
    return max(evaluated, key=lambda item: (item[2], -item[1]))


def _trim_candles_to_duration(
    candles: list[dict], duration: timedelta, candle_seconds: int,
) -> list[dict]:
    limit = max(ceil(duration.total_seconds() / candle_seconds), 1)
    return candles[-limit:]


def _candle_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _candle_tick_coverage_ratio(
    candle: dict,
    tick_seconds: int,
    server_time: datetime,
) -> float | None:
    """Return real publication-slot coverage for one observed candle."""

    if tick_seconds <= 0:
        return None
    start_time = _candle_datetime(candle["start_time"])
    end_time = _candle_datetime(candle["end_time"])
    if start_time > server_time:
        return None
    covered_until = min(end_time, server_time)
    covered_seconds = max((covered_until - start_time).total_seconds(), 0.0)
    if covered_seconds <= 0:
        return None
    if end_time <= server_time:
        expected = max(ceil(covered_seconds / tick_seconds), 1)
    else:
        # The in-progress candle includes a publication at its start and then
        # one at each completed five-minute boundary.
        expected = max(int(covered_seconds // tick_seconds) + 1, 1)
    observed = max(int(candle.get("tick_count") or 0), 0)
    return min(observed / expected, 1.0)


def _latest_partial_quality_candles(
    candles: list[dict],
    candle_seconds: int,
    tick_seconds: int,
    server_time: datetime,
) -> list[dict]:
    """Keep the newest consecutive hours with usable real tick coverage."""

    contiguous = _latest_contiguous_candles(candles, candle_seconds)
    qualified: list[dict] = []
    for candle in reversed(contiguous):
        ratio = _candle_tick_coverage_ratio(candle, tick_seconds, server_time)
        if ratio is None or ratio < SNAPSHOT_24H_MIN_PARTIAL_TICK_COVERAGE:
            break
        qualified.append(candle)
    qualified.reverse()
    return qualified


def _observed_tick_quality(
    candles: list[dict],
    tick_seconds: int,
    server_time: datetime,
) -> dict:
    """Measure distinct publication slots overall and inside every candle."""

    if not candles or tick_seconds <= 0:
        return {
            "coverage_ratio": 0.0,
            "minimum_candle_coverage_ratio": 0.0,
            "all_candles_meet_minimum": False,
        }
    expected_ticks = 0
    observed_ticks = 0
    candle_coverage_ratios: list[float] = []
    for candle in candles:
        start_time = _candle_datetime(candle["start_time"])
        end_time = _candle_datetime(candle["end_time"])
        ratio = _candle_tick_coverage_ratio(candle, tick_seconds, server_time)
        if ratio is None:
            continue
        covered_until = min(end_time, server_time)
        covered_seconds = max((covered_until - start_time).total_seconds(), 0.0)
        if end_time <= server_time:
            candle_expected = max(ceil(covered_seconds / tick_seconds), 1)
        else:
            candle_expected = max(int(covered_seconds // tick_seconds) + 1, 1)
        candle_observed = max(int(candle.get("tick_count") or 0), 0)
        expected_ticks += candle_expected
        observed_ticks += min(candle_observed, candle_expected)
        candle_coverage_ratios.append(ratio)
    if expected_ticks <= 0:
        return {
            "coverage_ratio": 0.0,
            "minimum_candle_coverage_ratio": 0.0,
            "all_candles_meet_minimum": False,
        }
    coverage_ratio = min(observed_ticks / expected_ticks, 1.0)
    minimum_candle_coverage = min(candle_coverage_ratios, default=0.0)
    return {
        "coverage_ratio": coverage_ratio,
        "minimum_candle_coverage_ratio": minimum_candle_coverage,
        "all_candles_meet_minimum": (
            bool(candle_coverage_ratios)
            and all(
                ratio >= SNAPSHOT_24H_MIN_TICK_COVERAGE
                for ratio in candle_coverage_ratios
            )
        ),
    }


def _range_coverage_requirements(duration: timedelta) -> tuple[int, float]:
    """Return distinct-day and elapsed-hour thresholds for a requested range.

    The small tolerance accommodates collector scheduling and rolling-window
    boundaries.  Long ranges also require observations on most UTC dates, so
    two distant points cannot make a sparse 30/90-day series appear complete.
    """
    duration_hours = duration.total_seconds() / 3600
    required_span_hours = duration_hours * RANGE_COVERAGE_RATIO
    duration_days = duration.total_seconds() / (24 * 60 * 60)
    required_days = (
        max(ceil(duration_days * RANGE_COVERAGE_RATIO), 1)
        if duration_days >= 1
        else 1
    )
    return required_days, required_span_hours


def _range_curve_status(observed_times: list[datetime], duration: timedelta) -> str:
    if len(observed_times) < 2:
        return "single" if observed_times else "unavailable"
    required_days, required_span_hours = _range_coverage_requirements(duration)
    day_count = len({item.date() for item in observed_times})
    span_hours = (max(observed_times) - min(observed_times)).total_seconds() / 3600
    return (
        "full"
        if day_count >= required_days and span_hours >= required_span_hours
        else "partial"
    )


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
    source_priority = {"kai": 0, "autodl": 1, "wod": 2}
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
        "observed_partial_low_cny": None,
        "observed_partial_high_cny": None,
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


def _kai_history_metrics(
    db: Session,
    identities: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], dict]:
    """Build ranking metrics from worker-cached official candles only."""

    requested = {
        (canonicalize_gpu(model) or model, normalize_gpu_variant(canonicalize_gpu(model) or model, variant))
        for model, variant in identities
    }
    if not requested:
        return {}
    models = {model for model, _ in requested}
    rows = db.query(MarketPriceCandle).filter(
        MarketPriceCandle.source == "kai",
        MarketPriceCandle.billing_mode == "ondemand",
        # Ranking is a seven-day daily metric. Minute/hour/four-hour cache
        # rows coexist in the same table and must never be mixed into it.
        MarketPriceCandle.interval_seconds == 24 * 60 * 60,
        MarketPriceCandle.gpu_model.in_(models),
    ).order_by(MarketPriceCandle.start_time.asc()).all()
    grouped: dict[tuple[str, str], list[MarketPriceCandle]] = defaultdict(list)
    for row in rows:
        identity = (
            canonicalize_gpu(row.gpu_model) or row.gpu_model,
            normalize_gpu_variant(canonicalize_gpu(row.gpu_model) or row.gpu_model, row.gpu_variant),
        )
        if identity in requested:
            grouped[identity].append(row)
    result: dict[tuple[str, str], dict] = {}
    for identity, series in grouped.items():
        selected = series[-7:]
        if not selected:
            continue
        first = Decimal(selected[0].open_price_cny)
        last = Decimal(selected[-1].close_price_cny)
        lows = [Decimal(row.low_price_cny) for row in selected]
        highs = [Decimal(row.high_price_cny) for row in selected]
        closes = [Decimal(row.close_price_cny) for row in selected]
        median_close = _median(_without_outliers(closes))
        day_count = len({row.start_time.date() for row in selected})
        span_hours = max((selected[-1].end_time - selected[0].start_time).total_seconds() / 3600, 0.0)
        complete = day_count >= MIN_RANGE_DAYS and span_hours >= MIN_RANGE_SPAN_HOURS
        change = float((last / first - Decimal("1")) * Decimal("100")) if complete and first > 0 else None
        volatility = float((max(highs) - min(lows)) / median_close * Decimal("100")) if complete and median_close > 0 else None
        result[identity] = {
            "volatility_7d": round(volatility, 2) if volatility is not None else None,
            "volatility_status": "available" if complete else "insufficient_history",
            "volatility_quality": "verified" if complete else "limited_sample",
            "history_day_count": day_count,
            "history_point_count": len(selected),
            "history_span_hours": round(span_hours, 1),
            "history_min_daily_sample_count": min((row.sample_count for row in selected), default=0),
            "history_bucket_count": len(selected),
            "history_coverage_status": "complete" if complete else "partial",
            "volatility_source_count": 1,
            "volatility_sources": ["kai"],
            "volatility_billing_mode": "ondemand",
            "volatility_method": "stored_official_ohlc_high_low_range_over_median_close",
            "change_7d_pct": round(change, 2) if change is not None else None,
            "range_low_cny": float(min(lows)) if complete else None,
            "range_high_cny": float(max(highs)) if complete else None,
            "observed_partial_low_cny": float(min(lows)),
            "observed_partial_high_cny": float(max(highs)),
            "flat_price_observed": min(lows) == max(highs),
            "history_provenance": {
                "kind": "official_historical_ohlc",
                "dataset_source": "market_price_candles",
                "upstream_provider": "kai",
                "collection_mode": "scheduled_database_agent",
                "live_component_included": False,
            },
        }
    return result


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
        "kai pricing": "kai",
        "kai_pricing": "kai",
        "vast.ai": "vast",
        "vastai": "vast",
        "auto dl": "autodl",
        "auto_dl": "autodl",
    }
    provider = aliases.get(provider, provider)
    comparable = {aliases.get(str(source).strip().lower(), str(source).strip().lower()) for source in live_sources}
    return bool(provider and provider in comparable)


def _source_states(db: Session, now: datetime) -> dict[str, str]:
    return {
        row.source: _source_state(row, now)
        for row in db.query(MarketSourceStatus).all()
        if row.enabled and row.source in SOURCE_NAMES
    }


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
        } for row in rows if row.enabled and row.source in SOURCE_NAMES],
        "history_items": [],
        "transport": kai_http_transport_snapshot(),
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
            "quote_sample_count": 0,
            "available_gpu_count": None,
            "inventory_available": None,
            "sample_semantics": "current_quote_observations_not_inventory",
            "billing_unit": "GPU_HOUR",
        })
        if row.source not in item["sources"]:
            item["sources"].append(row.source)
        item["sample_count"] += row.sample_count
        item["quote_sample_count"] += row.sample_count
    kai_metrics = _kai_history_metrics(db, grouped.keys())
    for key, item in grouped.items():
        item.update(kai_metrics.get(key) or metrics.get(key, _empty_metric()))
        item["seven_day_status"] = (
            "full" if item.get("history_coverage_status") == "complete" and item.get("change_7d_pct") is not None
            else "partial" if item.get("history_day_count", 0) > 0
            else "unavailable"
        )
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
    sources: str = "kai",
    db: Session = Depends(get_db),
):
    now = utcnow()
    allowed_sources = _kai_sources(sources)
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
    median_cny = _weighted_median(rows)
    # Prefer sources that actually contributed this model/variant.  When no
    # quote exists yet, fall back to the valid requested set, then to the
    # requested set itself so retry guidance remains source-specific.
    refresh_sources = {row.source for row in rows} or current_sources or allowed_sources
    return success({
        "server_time": _iso(now),
        "next_refresh_in": _next_market_refresh_seconds(refresh_sources),
        "gpu_model": canonical_model,
        "gpu_variant": selected_variant,
        "summary": {
            "median_price_cny": median_cny,
            "min_price_cny": min(cny_mins) if cny_mins else None,
            "max_price_cny": max(cny_maxes) if cny_maxes else None,
            "median_price_card_hours": _to_card_hours(median_cny),
            "min_price_card_hours": _to_card_hours(min(cny_mins) if cny_mins else None),
            "max_price_card_hours": _to_card_hours(max(cny_maxes) if cny_maxes else None),
            "sample_count": sum(row.sample_count for row in rows),
            "quote_sample_count": sum(row.sample_count for row in rows),
            "available_gpu_count": None,
            "inventory_available": None,
            "sample_semantics": "current_quote_observations_not_inventory",
            "billing_unit": "GPU_HOUR",
            "wallet_charge_unit": "CARD_HOUR",
            "card_hour_rmb_rate": float(_card_hour_rate()),
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
    sources: str = "kai",
    db: Session = Depends(get_db),
):
    if range not in MARKET_RANGE_DURATIONS:
        raise BizError("不支持的时间范围")
    allowed_sources = _kai_sources(sources)
    all_latest = _latest_rows(db)
    canonical_model = canonicalize_gpu(model) or model
    selected_variant = normalize_gpu_variant(
        canonical_model,
        variant if variant is not None else _pick_variant(all_latest, canonical_model),
    )
    variant_filters = gpu_variant_aliases(canonical_model, selected_variant)
    since = utcnow() - MARKET_RANGE_DURATIONS[range]
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
            "price_card_hours": _to_card_hours(row.median_price_cny),
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
            "curve_status": _range_curve_status(
                source_times[source], MARKET_RANGE_DURATIONS[range],
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
    sources: str = "kai",
    billing_mode: str = "ondemand",
    db: Session = Depends(get_db),
    external_product_id: str | None = None,
):
    normalized_sources = tuple(sorted(_kai_sources(sources)))
    cache_key = (
        "market_candles", model, variant or "", range, normalized_sources, billing_mode,
        external_product_id or "",
    )
    ttl_seconds = 300 if range in {"7d", "30d", "90d"} else 8
    payload = _cached_payload(
        db,
        cache_key,
        ttl_seconds,
        lambda: _price_candles_payload(
            model, variant, range, sources, billing_mode, db, external_product_id,
        ),
    )
    return success(payload)


def _relative_price_deviation(left: Decimal, right: Decimal) -> float:
    denominator = max(abs(left), abs(right), Decimal("0.01"))
    return float(abs(left - right) / denominator)


def _official_edge_price_gap(left: MarketPriceCandle, right: MarketPriceCandle) -> float:
    return _relative_price_deviation(
        Decimal(left.close_price_cny),
        Decimal(right.open_price_cny),
    )


def _older_edge_provenance(
    edge: MarketPriceCandle,
    neighbour: MarketPriceCandle,
) -> bool:
    edge_observed = edge.source_observed_at
    neighbour_observed = neighbour.source_observed_at
    if (
        edge_observed is None
        or neighbour_observed is None
        or edge_observed >= neighbour_observed
    ):
        return False
    edge_is_partial = "partial" in str(edge.data_quality or "").lower()
    version_changed = (edge.source_version or "") != (neighbour.source_version or "")
    return edge_is_partial or version_changed


def _quarantine_superseded_edge_candles(
    rows: list[MarketPriceCandle],
) -> tuple[list[MarketPriceCandle], dict]:
    """Remove only isolated edge buckets from an older official publication.

    This is a provenance quality gate, not an outlier filter. A large move from
    a current/full publication is retained. Two or more consecutive candles at
    a new level are also retained because they may represent a real repricing.
    Quarantined rows remain stored for auditability and are disclosed by the
    public response.
    """

    cleaned = list(rows)
    prefix_count = 0
    tail_count = 0
    if len(cleaned) >= 3:
        first, second, third = cleaned[0], cleaned[1], cleaned[2]
        if (
            _official_edge_price_gap(first, second) >= OFFICIAL_EDGE_PRICE_GAP_LIMIT
            and _official_edge_price_gap(second, third) < OFFICIAL_EDGE_PRICE_GAP_LIMIT
            and _older_edge_provenance(first, second)
        ):
            cleaned = cleaned[1:]
            prefix_count = 1
    if len(cleaned) >= 3:
        third_last, second_last, last = cleaned[-3], cleaned[-2], cleaned[-1]
        if (
            _official_edge_price_gap(second_last, last) >= OFFICIAL_EDGE_PRICE_GAP_LIMIT
            and _official_edge_price_gap(third_last, second_last) < OFFICIAL_EDGE_PRICE_GAP_LIMIT
            and _older_edge_provenance(last, second_last)
        ):
            cleaned = cleaned[:-1]
            tail_count = 1
    total = prefix_count + tail_count
    return cleaned, {
        "quarantined_candle_count": total,
        "quarantined_prefix_count": prefix_count,
        "quarantined_tail_count": tail_count,
        "quarantine_reason": "superseded_partial_edge_batch" if total else None,
    }


def _stored_resolution_consistency(
    db: Session,
    model: str,
    variant_filters: set[str],
    server_time: datetime,
) -> dict:
    """Compare closed native 1h OHLC with native 4h OHLC on exact windows.

    Four consecutive one-hour candles are aggregated using normal OHLC rules.
    Only an exact native four-hour window is compared; missing or shifted
    windows are ignored rather than interpolated.  Median deviations and a
    majority rule make the gate insensitive to a few upstream boundary quirks.
    """

    hourly_limit = RESOLUTION_COMPARISON_BUCKET_LIMIT * 4
    common_filters = (
        MarketPriceCandle.source == "kai",
        MarketPriceCandle.gpu_model == model,
        MarketPriceCandle.gpu_variant.in_(variant_filters),
        MarketPriceCandle.billing_mode == "ondemand",
        MarketPriceCandle.end_time <= server_time,
        or_(
            MarketPriceCandle.source_observed_at.is_(None),
            MarketPriceCandle.source_observed_at <= server_time,
        ),
    )
    hourly_rows = db.query(MarketPriceCandle).filter(
        *common_filters,
        MarketPriceCandle.interval_seconds == 60 * 60,
    ).order_by(MarketPriceCandle.start_time.desc()).limit(hourly_limit).all()
    reference_rows = db.query(MarketPriceCandle).filter(
        *common_filters,
        MarketPriceCandle.interval_seconds == RESOLUTION_REFERENCE_SECONDS,
    ).order_by(MarketPriceCandle.start_time.desc()).limit(
        RESOLUTION_COMPARISON_BUCKET_LIMIT,
    ).all()

    hourly_by_start = {row.start_time: row for row in hourly_rows}
    close_deviations: list[float] = []
    bucket_ohlc_deviations: list[float] = []
    large_deviation_count = 0
    one_hour = timedelta(hours=1)
    four_hours = timedelta(seconds=RESOLUTION_REFERENCE_SECONDS)
    for reference in reference_rows:
        if reference.end_time - reference.start_time != four_hours:
            continue
        components = [
            hourly_by_start.get(reference.start_time + one_hour * offset)
            for offset in range(4)
        ]
        if any(row is None for row in components):
            continue
        hourly = [row for row in components if row is not None]
        if any(
            row.end_time - row.start_time != one_hour
            or (index > 0 and hourly[index - 1].end_time != row.start_time)
            for index, row in enumerate(hourly)
        ) or hourly[-1].end_time != reference.end_time:
            continue

        aggregate = (
            Decimal(hourly[0].open_price_cny),
            max(Decimal(row.high_price_cny) for row in hourly),
            min(Decimal(row.low_price_cny) for row in hourly),
            Decimal(hourly[-1].close_price_cny),
        )
        native = (
            Decimal(reference.open_price_cny),
            Decimal(reference.high_price_cny),
            Decimal(reference.low_price_cny),
            Decimal(reference.close_price_cny),
        )
        metric_deviations = [
            _relative_price_deviation(aggregate_value, native_value)
            for aggregate_value, native_value in zip(aggregate, native)
        ]
        close_deviation = metric_deviations[-1]
        bucket_deviation = max(metric_deviations)
        close_deviations.append(close_deviation)
        bucket_ohlc_deviations.append(bucket_deviation)
        if bucket_deviation > RESOLUTION_LARGE_BUCKET_DEVIATION_LIMIT:
            large_deviation_count += 1

    compared_bucket_count = len(close_deviations)
    quality = {
        "status": "insufficient_overlap",
        "requested_bucket_seconds": 60 * 60,
        "reference_bucket_seconds": RESOLUTION_REFERENCE_SECONDS,
        "compared_bucket_count": compared_bucket_count,
        "minimum_comparison_bucket_count": RESOLUTION_MIN_COMPARISON_BUCKETS,
        "median_close_deviation_ratio": None,
        "median_ohlc_deviation_ratio": None,
        "large_deviation_bucket_count": large_deviation_count,
        "thresholds": {
            "median_close_deviation_ratio": RESOLUTION_MEDIAN_CLOSE_DEVIATION_LIMIT,
            "median_ohlc_deviation_ratio": RESOLUTION_MEDIAN_OHLC_DEVIATION_LIMIT,
            "large_bucket_deviation_ratio": RESOLUTION_LARGE_BUCKET_DEVIATION_LIMIT,
            "large_bucket_share": RESOLUTION_LARGE_BUCKET_RATIO_LIMIT,
        },
    }
    if compared_bucket_count < RESOLUTION_MIN_COMPARISON_BUCKETS:
        return quality

    median_close_deviation = float(median(close_deviations))
    # A median of all four flattened OHLC fields can hide a repeatedly wrong
    # high or low behind otherwise similar opens and closes. Compare the worst
    # OHLC field per bucket, then take its median across the overlap instead.
    median_ohlc_deviation = float(median(bucket_ohlc_deviations))
    large_deviation_ratio = large_deviation_count / compared_bucket_count
    inconsistent = (
        median_close_deviation > RESOLUTION_MEDIAN_CLOSE_DEVIATION_LIMIT
        or median_ohlc_deviation > RESOLUTION_MEDIAN_OHLC_DEVIATION_LIMIT
        or (
            large_deviation_count >= 3
            and large_deviation_ratio >= RESOLUTION_LARGE_BUCKET_RATIO_LIMIT
        )
    )
    quality.update({
        "status": "inconsistent" if inconsistent else "consistent",
        "median_close_deviation_ratio": round(median_close_deviation, 6),
        "median_ohlc_deviation_ratio": round(median_ohlc_deviation, 6),
        "large_deviation_bucket_ratio": round(large_deviation_ratio, 6),
    })
    return quality


def _aggregate_contiguous_hourly_thirty_day_fallback(
    db: Session,
    model: str,
    variant: str,
    variant_filters: set[str],
    server_time: datetime,
    duration: timedelta,
) -> list[MarketPriceCandle]:
    """Aggregate only real, complete UTC 1h groups into a recent 4h suffix.

    This is a read-time safety fallback for a native 4h publication that does
    not match its overlapping native 1h history. Missing hours are never
    filled, and older buckets across a gap are not connected to the suffix.
    The returned ORM objects are transient and are never added to the session.
    """

    one_hour_seconds = 60 * 60
    one_hour = timedelta(seconds=one_hour_seconds)
    four_hours = timedelta(seconds=RESOLUTION_REFERENCE_SECONDS)
    expected_hour_count = max(ceil(duration.total_seconds() / one_hour_seconds), 1)
    # Three extra hours are enough to retain the last complete UTC-aligned 4h
    # window when the newest stored hour belongs to the next partial window.
    hourly_rows = db.query(MarketPriceCandle).filter(
        MarketPriceCandle.source == "kai",
        MarketPriceCandle.gpu_model == model,
        MarketPriceCandle.gpu_variant.in_(variant_filters),
        MarketPriceCandle.billing_mode == "ondemand",
        MarketPriceCandle.interval_seconds == one_hour_seconds,
        MarketPriceCandle.end_time <= server_time,
        or_(
            MarketPriceCandle.source_observed_at.is_(None),
            MarketPriceCandle.source_observed_at <= server_time,
        ),
    ).order_by(MarketPriceCandle.start_time.desc()).limit(
        expected_hour_count + 3,
    ).all()
    if not hourly_rows:
        return []

    hourly_by_start = {row.start_time: row for row in hourly_rows}
    aggregated: list[MarketPriceCandle] = []
    for start_time in sorted(hourly_by_start):
        # KAI native 4h buckets are aligned to 00/04/08/12/16/20 UTC.
        if (
            start_time.minute != 0
            or start_time.second != 0
            or start_time.microsecond != 0
            or start_time.hour % 4 != 0
        ):
            continue
        components = [
            hourly_by_start.get(start_time + one_hour * offset)
            for offset in range(4)
        ]
        if any(row is None for row in components):
            continue
        hourly = [row for row in components if row is not None]
        if any(
            row.end_time - row.start_time != one_hour
            or (index > 0 and hourly[index - 1].end_time != row.start_time)
            for index, row in enumerate(hourly)
        ) or hourly[-1].end_time != start_time + four_hours:
            continue

        source_observed_values = [
            row.source_observed_at for row in hourly if row.source_observed_at is not None
        ]
        source_versions = {
            row.source_version for row in hourly if row.source_version is not None
        }
        aggregated.append(MarketPriceCandle(
            source="kai",
            gpu_model=model,
            gpu_variant=variant,
            billing_mode="ondemand",
            interval_seconds=RESOLUTION_REFERENCE_SECONDS,
            start_time=start_time,
            end_time=start_time + four_hours,
            open_price_cny=Decimal(hourly[0].open_price_cny),
            high_price_cny=max(Decimal(row.high_price_cny) for row in hourly),
            low_price_cny=min(Decimal(row.low_price_cny) for row in hourly),
            close_price_cny=Decimal(hourly[-1].close_price_cny),
            # Sample count describes the common usable cohort, not four times
            # the number of products. Observation count remains additive.
            sample_count=min(row.sample_count for row in hourly),
            observation_count=sum(row.observation_count for row in hourly),
            method="official_hourly_aggregated_four_hour",
            data_quality="official_hourly_aggregate",
            source_version=next(iter(source_versions)) if len(source_versions) == 1 else None,
            signature=f"derived-hourly-{int(start_time.timestamp())}",
            source_observed_at=max(source_observed_values) if source_observed_values else None,
            collected_at=max(row.collected_at for row in hourly),
            updated_at=max(row.updated_at for row in hourly),
        ))

    if not aggregated:
        return []
    # Keep only the latest gap-free 4h suffix. A missing historical window is
    # represented by absent older candles, which the fixed chart viewport
    # renders as blank space rather than a fabricated connecting segment.
    contiguous = [aggregated[-1]]
    newer = aggregated[-1]
    for row in reversed(aggregated[:-1]):
        if row.end_time != newer.start_time:
            break
        contiguous.append(row)
        newer = row
    contiguous.reverse()
    expected_bucket_count = max(
        ceil(duration.total_seconds() / RESOLUTION_REFERENCE_SECONDS), 1,
    )
    return contiguous[-expected_bucket_count:]


def _stored_kai_candle_payload(
    db: Session,
    model: str,
    variant: str,
    range_name: str,
    duration: timedelta,
) -> dict | None:
    requested_interval_seconds = STORED_CANDLE_INTERVALS.get(range_name)
    interval_candidates = STORED_CANDLE_INTERVAL_CANDIDATES.get(range_name)
    if requested_interval_seconds is None or interval_candidates is None:
        return None
    variant_filters = gpu_variant_aliases(model, variant)
    server_time = utcnow()
    latest_live = db.query(MarketPriceSnapshot).filter(
        MarketPriceSnapshot.source == "kai",
        MarketPriceSnapshot.gpu_model == model,
        MarketPriceSnapshot.gpu_variant.in_(variant_filters),
        MarketPriceSnapshot.billing_mode == "ondemand",
        MarketPriceSnapshot.median_price_cny.isnot(None),
        MarketPriceSnapshot.observed_at <= server_time,
    ).order_by(MarketPriceSnapshot.observed_at.desc()).first()
    lag_reference = latest_live.observed_at if latest_live else server_time
    # The public range owns one fixed bucket size. Only the 30-day native 4h
    # publication is checked against overlapping native 1h history. Shorter
    # public ranges retain their fixed 1h contract without cross-resolution
    # replacement.
    resolution_quality = (
        _stored_resolution_consistency(db, model, variant_filters, server_time)
        if range_name == "30d"
        else None
    )
    hourly_resolution_fallback: list[MarketPriceCandle] | None = None
    candidates: list[tuple[tuple, dict]] = []
    sync_state = None
    sync_state_loaded = False

    for interval_seconds in interval_candidates:
        interval = timedelta(seconds=interval_seconds)
        expected_bucket_count = max(ceil(duration.total_seconds() / interval_seconds), 1)
        # The descending LIMIT stays bounded to the requested window plus two
        # audit buckets. The small overfetch lets a quarantined stale tail be
        # replaced by the immediately preceding verified bucket.
        stored = db.query(MarketPriceCandle).filter(
            MarketPriceCandle.source == "kai",
            MarketPriceCandle.gpu_model == model,
            MarketPriceCandle.gpu_variant.in_(variant_filters),
            MarketPriceCandle.billing_mode == "ondemand",
            MarketPriceCandle.interval_seconds == interval_seconds,
            MarketPriceCandle.end_time <= server_time,
            or_(
                MarketPriceCandle.source_observed_at.is_(None),
                MarketPriceCandle.source_observed_at <= server_time,
            ),
        ).order_by(MarketPriceCandle.start_time.desc()).limit(
            expected_bucket_count + OFFICIAL_EDGE_OVERFETCH_BUCKETS,
        ).all()
        if not stored:
            continue
        if not sync_state_loaded:
            sync_state = db.query(MarketCandleSyncStatus).filter(
                MarketCandleSyncStatus.source == "kai",
            ).one_or_none()
            sync_state_loaded = True
        stored.reverse()
        if stored[-1].end_time - stored[-1].start_time != interval:
            continue

        # A gap ends the public series. Never connect older observations across
        # a missing official bucket just to make the requested range look full.
        rows = [stored[-1]]
        newer = stored[-1]
        for row in reversed(stored[:-1]):
            if row.end_time - row.start_time != interval or row.end_time != newer.start_time:
                break
            rows.append(row)
            newer = row
        rows.reverse()

        # Inspect the exact public window before computing coverage. If a stale
        # tail is quarantined, an older adjacent candle can safely refill the
        # beginning without bridging a missing timestamp. A quarantined prefix
        # is left partial because bridging over its timestamp would be false.
        contiguous_rows = rows
        candidate_rows = contiguous_rows[-expected_bucket_count:]
        rows, quarantine = _quarantine_superseded_edge_candles(candidate_rows)
        if (
            quarantine["quarantined_tail_count"]
            and not quarantine["quarantined_prefix_count"]
            and len(rows) < expected_bucket_count
        ):
            public_start_index = len(contiguous_rows) - len(candidate_rows)
            needed = expected_bucket_count - len(rows)
            refill = contiguous_rows[max(public_start_index - needed, 0):public_start_index]
            if (
                len(refill) == needed
                and rows
                and refill[-1].end_time == rows[0].start_time
            ):
                rows = refill + rows

        resolution_fallback = False
        if (
            range_name == "30d"
            and resolution_quality is not None
            and resolution_quality["status"] == "inconsistent"
        ):
            if hourly_resolution_fallback is None:
                hourly_resolution_fallback = (
                    _aggregate_contiguous_hourly_thirty_day_fallback(
                        db, model, variant, variant_filters, server_time, duration,
                    )
                )
            # Once native 4h history has failed the overlap gate, it must never
            # win merely because it covers all 180 buckets. If real hourly
            # history cannot produce even one complete 4h group, let the caller
            # continue to its ordinary sparse-history path instead.
            if not hourly_resolution_fallback:
                continue
            rows = hourly_resolution_fallback
            resolution_fallback = True
            quarantine = {
                "quarantined_candle_count": 0,
                "quarantined_prefix_count": 0,
                "quarantined_tail_count": 0,
                "quarantine_reason": None,
            }

        span_seconds = max((rows[-1].end_time - rows[0].start_time).total_seconds(), 0.0)
        duration_seconds = max(duration.total_seconds(), 1.0)
        coverage_ratio = min(
            len(rows) / expected_bucket_count,
            span_seconds / duration_seconds,
            1.0,
        )
        temporal_complete = (
            len(rows) == expected_bucket_count
            and span_seconds == duration.total_seconds()
        )
        history_lag_seconds = max(int((lag_reference - rows[-1].end_time).total_seconds()), 0)
        stale_after_seconds = int(max(
            interval_seconds * 2,
            min(duration.total_seconds() / 2, 24 * 60 * 60),
        ))
        freshness_status = (
            "stale" if history_lag_seconds > stale_after_seconds else "current"
        )
        # Even if a deployment eventually accumulates 30 days of hourly data,
        # this remains a disclosed safety fallback rather than claiming that
        # the quarantined native 4h publication was verified.
        temporal_current = (
            temporal_complete
            and freshness_status == "current"
            and not resolution_fallback
        )
        strict_complete = (
            interval_seconds == requested_interval_seconds
            and temporal_current
        )
        coverage_state = (
            "full" if temporal_current
            else "single" if len(rows) == 1
            else "partial"
        )
        history_status = (
            "available" if temporal_current
            else "single_observation" if len(rows) == 1
            else "partial_history"
        )
        fallback_reason = None
        if resolution_fallback:
            fallback_reason = "native_four_hour_inconsistent_with_hourly_overlap"
        elif interval_seconds != requested_interval_seconds:
            fallback_reason = "requested_resolution_unavailable_or_incomplete"
        resolution_consistency_status = (
            resolution_quality["status"]
            if resolution_quality is not None
            else "not_evaluated"
        )
        payload = {
            "server_time": _iso(server_time),
            "gpu_model": model,
            "gpu_variant": variant,
            "billing_mode": "ondemand",
            "range": range_name,
            "requested_bucket_seconds": requested_interval_seconds,
            "bucket_seconds": interval_seconds,
            "tick_seconds": interval_seconds,
            "resolution_status": (
                "fallback_aggregated_from_hourly" if resolution_fallback
                else "requested" if interval_seconds == requested_interval_seconds
                else "fallback_official_resolution"
            ),
            "resolution_fallback_reason": fallback_reason,
            "partial_reason": fallback_reason if resolution_fallback else None,
            "resolution_consistency_status": resolution_consistency_status,
            "resolution_consistency": resolution_quality,
            "aggregation_source_bucket_seconds": (
                60 * 60 if resolution_fallback else None
            ),
            "observed_bucket_coverage_ratio": round(coverage_ratio, 4),
            "expected_bucket_count": expected_bucket_count,
            "method": rows[-1].method,
            "is_interpolated": False,
            "requested_sources": ["kai"],
            "selected_source": "kai",
            "history_status": history_status,
            "curve_status": coverage_state,
            "coverage_class": coverage_state,
            # Coverage and resolution are separate facts. A real coarser
            # fallback can still cover the complete requested time window;
            # ``resolution_status`` already discloses that it is not the
            # preferred bucket size.
            "history_coverage_status": "complete" if temporal_current else coverage_state,
            "coverage_day_count": len({row.start_time.date() for row in rows}),
            "coverage_span_hours": round(span_seconds / 3600, 1),
            "data_quality": rows[-1].data_quality,
            **quarantine,
            "provenance": {
                "kind": (
                    "stored_official_hourly_aggregated_ohlc" if resolution_fallback
                    else "stored_official_historical_ohlc"
                ),
                "dataset_source": "market_price_candles",
                "upstream_provider": "kai",
                "collection_mode": "scheduled_database_agent",
                "source_version": rows[-1].source_version,
                "source_observed_at": _iso(rows[-1].source_observed_at),
                "history_as_of": _iso(rows[-1].end_time),
                "history_lag_seconds": history_lag_seconds,
                "history_freshness_status": freshness_status,
                "history_stale_after_seconds": stale_after_seconds,
                "temporal_coverage_status": "complete" if temporal_complete else "partial",
                "resolution_fallback_reason": fallback_reason,
                "partial_reason": fallback_reason if resolution_fallback else None,
                "resolution_consistency_status": resolution_consistency_status,
                "aggregation_source_bucket_seconds": (
                    60 * 60 if resolution_fallback else None
                ),
                "native_four_hour_quarantined": resolution_fallback,
                "last_database_sync_at": _iso(sync_state.last_success_at) if sync_state else None,
                "live_component_included": False,
                **quarantine,
            },
            "latest_live_price_cny": float(latest_live.median_price_cny) if latest_live else None,
            "latest_live_observed_at": _iso(latest_live.observed_at) if latest_live else None,
            # Stored official OHLC is a cross-region historical aggregate,
            # while the live value is the current offer-pool median. Keep both
            # visible, but never splice the live value into this curve.
            "latest_live_comparable_to_history": False if latest_live else None,
            "candles": [{
                "start_time": _iso(row.start_time),
                "end_time": _iso(row.end_time),
                "open_price_cny": float(row.open_price_cny),
                "high_price_cny": float(row.high_price_cny),
                "low_price_cny": float(row.low_price_cny),
                "close_price_cny": float(row.close_price_cny),
                "sample_count": row.sample_count,
                "observation_count": row.observation_count,
                "sources": ["kai"],
            } for row in rows],
        }
        # A complete fresh duration wins first. Exact requested resolution then
        # wins ties; otherwise compare real coverage and freshness.
        score = (
            temporal_current,
            strict_complete,
            freshness_status == "current",
            coverage_ratio,
            -history_lag_seconds,
            interval_seconds == requested_interval_seconds,
        )
        candidates.append((score, payload))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _price_candles_payload(
    model: str,
    variant: str | None,
    range: str,  # noqa: A002
    sources: str,
    billing_mode: str,
    db: Session,
    external_product_id: str | None = None,
) -> dict:
    """Return observed OHLC candles for the selected GPU market.

    Candles use real stored source medians only. A missing time bucket remains
    missing instead of being filled with a generated line segment.
    """
    if range not in MARKET_CANDLE_CONFIG:
        raise BizError("不支持的时间范围")
    allowed_sources = _kai_sources(sources)
    duration, candle_seconds, tick_seconds = MARKET_CANDLE_CONFIG[range]
    canonical_model = canonicalize_gpu(model) or model
    picked_variant = variant if variant is not None else _pick_variant(_latest_rows(db), canonical_model)
    selected_variant = normalize_gpu_variant(canonical_model, picked_variant)
    if external_product_id:
        product = db.query(Product).filter(
            Product.market_source == "kai",
            Product.external_product_id == external_product_id,
        ).one_or_none()
        if product is None:
            raise BizError("资源标识不存在或报价已失效", status_code=404)
        product_model = canonicalize_gpu(product.gpu_model) or product.gpu_model
        product_variant = normalize_gpu_variant(product_model, product.memory)
        if product_model != canonical_model or product_variant != selected_variant:
            raise BizError("资源标识与请求的 GPU 型号不匹配", status_code=400)
    stored_payload = None
    if (
        "kai" in allowed_sources
        and billing_mode == "ondemand"
        and range in STORED_CANDLE_INTERVALS
        and range != "6h"
    ):
        stored_payload = _stored_kai_candle_payload(
            db, canonical_model, selected_variant, range, duration,
        )
        if stored_payload is not None and range != "24h":
            return _with_card_hour_candles(stored_payload)
    variant_filters = gpu_variant_aliases(canonical_model, selected_variant)
    requested_at = utcnow()
    since = requested_at - duration
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
        MarketPriceSnapshot.observed_at <= requested_at,
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

    required_coverage_days, required_coverage_span_hours = _range_coverage_requirements(duration)
    # A request may name several acceptable providers, but a temporal series
    # must still come from one provider. Select the strongest real series and
    # expose the choice instead of blending unrelated provider price levels.
    all_live_rows = list(rows)
    rows_by_source: dict[str, list] = defaultdict(list)
    for row in all_live_rows:
        rows_by_source[row.source].append(row)
    source_priority = {"kai": 3, "autodl": 2, "wod": 1}
    selected_live_source = max(
        rows_by_source,
        key=lambda source: (
            coverage(rows_by_source[source])[0] >= required_coverage_days
            and coverage(rows_by_source[source])[1] >= required_coverage_span_hours,
            coverage(rows_by_source[source])[1],
            coverage(rows_by_source[source])[0],
            coverage(rows_by_source[source])[2],
            source_priority.get(source, 0),
        ),
        default=None,
    )
    live_rows = list(rows_by_source.get(selected_live_source, []))
    coverage_day_count, coverage_span_hours, _ = coverage(live_rows)
    coverage_complete = (
        len(live_rows) >= 2
        and coverage_day_count >= required_coverage_days
        and coverage_span_hours >= required_coverage_span_hours
    )
    history_status = (
        "available"
        if coverage_complete
        else "partial_history"
        if len(live_rows) >= 2
        else "single_observation"
        if live_rows
        else "unavailable"
    )
    coverage_status = (
        "complete"
        if coverage_complete
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
    requested_candle_seconds = candle_seconds
    observed_bucket_density = None
    if range in MARKET_INTRADAY_BUCKET_CANDIDATES:
        candles, candle_seconds, observed_bucket_density = _select_observed_candle_resolution(
            candle_rows,
            MARKET_INTRADAY_BUCKET_CANDIDATES[range],
            tick_seconds,
        )
        tick_seconds = min(tick_seconds, candle_seconds)
    else:
        candles = _build_market_candles(candle_rows, candle_seconds, tick_seconds)
    if (
        range == "6h"
        and "kai" in allowed_sources
        and billing_mode == "ondemand"
        and (
            coverage_status != "complete"
            or observed_bucket_density is None
            or observed_bucket_density < RANGE_COVERAGE_RATIO
        )
    ):
        stored_payload = _stored_kai_candle_payload(
            db, canonical_model, selected_variant, range, duration,
        )
        if (
            stored_payload is not None
            and stored_payload.get("history_coverage_status") == "complete"
        ):
            return _with_card_hour_candles(stored_payload)
    if range == "7d" and "kai" in allowed_sources and billing_mode == "ondemand":
        contiguous_candles = _latest_contiguous_candles(candles, candle_seconds)
        latest_snapshot_at = max(
            (row.observed_at for row in live_rows),
            default=None,
        )
        snapshot_series_is_recent = (
            latest_snapshot_at is not None
            and latest_snapshot_at >= requested_at - timedelta(seconds=candle_seconds)
        )
        if (
            len(contiguous_candles) >= MIN_SEVEN_DAY_SNAPSHOT_CANDLES
            and snapshot_series_is_recent
        ):
            candles = contiguous_candles
        else:
            stored_payload = _stored_kai_candle_payload(
                db, canonical_model, selected_variant, range, duration,
            )
            if stored_payload is not None:
                return _with_card_hour_candles(stored_payload)
            # Keep the public seven-day contract at one-hour candles. Missing
            # hours stay missing and the response remains explicitly partial;
            # changing to daily bars made identical chart tabs look unrelated.
    candles = _trim_candles_to_duration(candles, duration, candle_seconds)
    expected_bucket_count = None
    observed_tick_coverage = None
    minimum_candle_tick_coverage = None
    snapshot_series_is_recent = None
    snapshot_candidate_status = None
    if range in {"24h", "7d", "30d"}:
        expected_bucket_count = max(
            ceil(duration.total_seconds() / requested_candle_seconds), 1,
        )
        contiguous_candles = _latest_contiguous_candles(candles, candle_seconds)
        strict_snapshot_requirements = True
        partial_snapshot_candles: list[dict] = []
        partial_snapshot_ready = False
        if range == "24h":
            latest_snapshot_at = max(
                (row.observed_at for row in live_rows),
                default=None,
            )
            snapshot_series_is_recent = (
                latest_snapshot_at is not None
                and latest_snapshot_at >= requested_at - timedelta(
                    seconds=SNAPSHOT_24H_MAX_LAG_SECONDS,
                )
            )
            tick_quality = _observed_tick_quality(
                candles, tick_seconds, requested_at,
            )
            observed_tick_coverage = tick_quality["coverage_ratio"]
            minimum_candle_tick_coverage = tick_quality["minimum_candle_coverage_ratio"]
            strict_snapshot_requirements = (
                expected_bucket_count == SNAPSHOT_24H_EXPECTED_CANDLES
                and snapshot_series_is_recent
                and observed_tick_coverage >= SNAPSHOT_24H_MIN_TICK_COVERAGE
                and tick_quality["all_candles_meet_minimum"]
            )
            partial_snapshot_candles = _latest_partial_quality_candles(
                candles, candle_seconds, tick_seconds, requested_at,
            )
            partial_snapshot_ready = (
                candle_seconds == requested_candle_seconds
                and snapshot_series_is_recent
                and len(candles) < expected_bucket_count
                and len(partial_snapshot_candles) >= SNAPSHOT_24H_MIN_PARTIAL_CANDLES
            )
        strict_complete = (
            candle_seconds == requested_candle_seconds
            and len(candles) == expected_bucket_count
            and len(contiguous_candles) == expected_bucket_count
            and strict_snapshot_requirements
        )
        if range == "24h":
            snapshot_candidate_status = (
                "ready"
                if strict_complete
                else "building"
                if partial_snapshot_ready
                else "insufficient_five_minute_coverage"
            )
            use_stored_fallback = (
                not strict_complete
                and stored_payload is not None
                and (
                    stored_payload.get("history_coverage_status") == "complete"
                    or not partial_snapshot_ready
                )
            )
            if use_stored_fallback:
                # Do not replace a complete 24-hour official series with only
                # the first few locally collected hours after a new deployment.
                # The two indices remain separate: the chart uses the complete
                # official series until the five-minute offer-pool collector has
                # built its own complete rolling day, then switches wholesale.
                stored_payload["snapshot_candidate_status"] = snapshot_candidate_status
                stored_payload["snapshot_candidate_candle_count"] = len(candles)
                stored_payload["snapshot_candidate_expected_candle_count"] = expected_bucket_count
                stored_payload["snapshot_candidate_tick_coverage_ratio"] = round(
                    observed_tick_coverage or 0.0, 4,
                )
                stored_payload["snapshot_candidate_minimum_hour_coverage_ratio"] = round(
                    minimum_candle_tick_coverage or 0.0, 4,
                )
                stored_provenance = stored_payload.get("provenance")
                if isinstance(stored_provenance, dict):
                    stored_provenance["snapshot_candidate_status"] = snapshot_candidate_status
                return _with_card_hour_candles(stored_payload)
            if partial_snapshot_ready:
                # Prefer the newest truthful one-hour suffix while the local
                # five-minute collector builds the full rolling day only when
                # no complete official one-hour window is available. The UI
                # exposes its partial coverage; independent indices are never
                # spliced into one curve.
                candles = partial_snapshot_candles
                contiguous_candles = list(partial_snapshot_candles)
                tick_quality = _observed_tick_quality(
                    candles, tick_seconds, requested_at,
                )
                observed_tick_coverage = tick_quality["coverage_ratio"]
                minimum_candle_tick_coverage = tick_quality[
                    "minimum_candle_coverage_ratio"
                ]
            elif not strict_complete:
                if stored_payload is not None:
                    stored_payload["snapshot_candidate_status"] = snapshot_candidate_status
                    stored_payload["snapshot_candidate_candle_count"] = len(candles)
                    stored_payload["snapshot_candidate_expected_candle_count"] = expected_bucket_count
                    stored_payload["snapshot_candidate_tick_coverage_ratio"] = round(
                        observed_tick_coverage or 0.0, 4,
                    )
                    stored_payload["snapshot_candidate_minimum_hour_coverage_ratio"] = round(
                        minimum_candle_tick_coverage or 0.0, 4,
                    )
                    stored_provenance = stored_payload.get("provenance")
                    if isinstance(stored_provenance, dict):
                        stored_provenance["snapshot_candidate_status"] = snapshot_candidate_status
                    return _with_card_hour_candles(stored_payload)
        history_status = (
            "available" if strict_complete
            else "partial_history" if len(candles) >= 2
            else "single_observation" if candles
            else "unavailable"
        )
        coverage_status = (
            "complete" if strict_complete
            else "partial" if len(candles) >= 2
            else "single" if candles
            else "unavailable"
        )
        if range == "24h":
            if provenance is not None:
                provenance["publication_interval_seconds"] = tick_seconds
                provenance["observed_tick_coverage_ratio"] = round(
                    observed_tick_coverage or 0.0, 4,
                )
                provenance["minimum_hour_tick_coverage_ratio"] = round(
                    minimum_candle_tick_coverage or 0.0, 4,
                )
                provenance["coverage_quality"] = (
                    "verified" if coverage_status == "complete" else "limited_sample"
                )
    curve_status = (
        "full"
        if candles and coverage_status == "complete"
        else "partial"
        if len(candles) >= 2
        else "single"
        if len(candles) == 1
        else "unavailable"
    )
    return _with_card_hour_candles({
        "server_time": _iso(requested_at),
        "gpu_model": canonical_model,
        "gpu_variant": selected_variant,
        "billing_mode": billing_mode,
        "range": range,
        "requested_bucket_seconds": requested_candle_seconds,
        "bucket_seconds": candle_seconds,
        "tick_seconds": tick_seconds,
        "resolution_status": (
            "requested"
            if candle_seconds == requested_candle_seconds
            else "coarsened_for_observation_density"
        ),
        "observed_bucket_coverage_ratio": (
            round(observed_bucket_density, 4)
            if observed_bucket_density is not None
            else None
        ),
        "observed_tick_coverage_ratio": (
            round(observed_tick_coverage, 4)
            if observed_tick_coverage is not None
            else None
        ),
        "snapshot_series_is_recent": snapshot_series_is_recent,
        "minimum_hour_tick_coverage_ratio": (
            round(minimum_candle_tick_coverage, 4)
            if minimum_candle_tick_coverage is not None
            else None
        ),
        "snapshot_candidate_status": snapshot_candidate_status,
        "expected_bucket_count": expected_bucket_count,
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
        "latest_live_comparable_to_history": True if latest_live_price_cny is not None else None,
        "candles": candles,
    })


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
    kai_metrics = _kai_history_metrics(db, grouped.keys())
    cutoff = now - timedelta(seconds=max(int(settings.PRODUCT_OFFER_MAX_AGE_SECONDS), 60))
    product_regions: dict[tuple[str, str], set[str]] = defaultdict(set)
    product_locations: dict[tuple[str, str], set[str]] = defaultdict(set)
    listed_quote_counts: Counter = Counter()
    for product in db.query(Product).filter(
        Product.market_source == "kai",
        Product.status == "on",
        Product.price_updated_at.isnot(None),
        Product.price_updated_at >= cutoff,
    ).all():
        product_model = canonicalize_gpu(product.gpu_model) or product.gpu_model
        product_variant = normalize_gpu_variant(product_model, product.memory)
        identity = (product_model, product_variant)
        product_regions[identity].add(map_region(product.city, product.country_code)[0])
        location = str(product.city or "").strip()
        if location:
            product_locations[identity].add(location)
        listed_quote_counts[identity] += 1
    items = []
    for (model, variant), rows in grouped.items():
        current = _weighted_median(rows)
        old_rows = comparison.get((model, variant), [])
        old_price = _weighted_median(old_rows)
        change = round((current / old_price - 1) * 100, 2) if current is not None and old_price else None
        metric = kai_metrics.get((model, variant)) or metrics.get((model, variant), _empty_metric())
        min_values = [float(row.min_price_cny) for row in rows if row.min_price_cny is not None]
        max_values = [float(row.max_price_cny) for row in rows if row.max_price_cny is not None]
        p25_values = [float(row.p25_price) for row in rows if row.currency == "CNY"]
        p75_values = [float(row.p75_price) for row in rows if row.currency == "CNY"]
        seven_day_status = (
            "full" if metric.get("history_coverage_status") == "complete" and metric.get("change_7d_pct") is not None
            else "partial" if metric.get("history_day_count", 0) > 0
            else "unavailable"
        )
        quote_sample_count = sum(row.sample_count for row in rows)
        items.append({
            "gpu_model": model,
            "gpu_variant": variant,
            "median_price_cny": current,
            "min_price_cny": min(min_values) if min_values else None,
            "max_price_cny": max(max_values) if max_values else None,
            "p25_price_cny": min(p25_values) if p25_values else None,
            "p75_price_cny": max(p75_values) if p75_values else None,
            "median_price_card_hours": _to_card_hours(current),
            "min_price_card_hours": _to_card_hours(min(min_values) if min_values else None),
            "max_price_card_hours": _to_card_hours(max(max_values) if max_values else None),
            "p25_price_card_hours": _to_card_hours(min(p25_values) if p25_values else None),
            "p75_price_card_hours": _to_card_hours(max(p75_values) if p75_values else None),
            "change_24h": change,
            **metric,
            "seven_day_status": seven_day_status,
            "sample_count": quote_sample_count,
            "quote_sample_count": quote_sample_count,
            "listed_quote_count": listed_quote_counts[(model, variant)],
            "region_count": len(product_regions[(model, variant)]),
            "location_count": len(product_locations[(model, variant)]),
            "available_gpu_count": None,
            "inventory_available": None,
            "sample_semantics": "current_quote_observations_not_inventory",
            "billing_unit": "GPU_HOUR",
            "source_count": 1,
            "sources": ["kai"],
            "market_status": source_states.get("kai", "unavailable"),
            "hot_eligible": metric["volatility_7d"] is not None,
        })
    items.sort(key=lambda item: (
        not item["hot_eligible"],
        item["volatility_quality"] != "verified",
        -(item["volatility_7d"] or 0),
        -abs(item["change_24h"] or 0),
        -item["quote_sample_count"],
        -item["region_count"],
        item["gpu_model"],
        item["gpu_variant"],
    ))
    return {
        "server_time": _iso(now),
        "items": items,
        "source_states": source_states,
        "source": "kai",
        "billing_unit": "GPU_HOUR",
        "wallet_charge_unit": "CARD_HOUR",
        "card_hour_rmb_rate": float(_card_hour_rate()),
        "sample_semantics": "current_quote_observations_not_inventory",
    }
