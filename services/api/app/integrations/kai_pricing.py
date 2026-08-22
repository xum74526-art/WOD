"""Validated client for KAI's public GPU card-hour pricing API.

The integration deliberately keeps KAI's identity separate from every other
provider.  Current quotes and historical candles are accepted only when their
published schema, unit, currency and freshness are explicit; no missing value
is generated or borrowed from a legacy Vast snapshot.
"""

from __future__ import annotations

import atexit
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
import time
from typing import Any, Callable, Iterable, TypeVar
from urllib.parse import quote, urlencode

import httpx

from app.core.config import settings
from app.services.gpu_catalog import (
    canonicalize_gpu,
    memory_variant_from_text,
    normalize_gpu_variant,
)


SOURCE_KEY = "kai"
SOURCE_NAME = "KAI GPU Pricing"
CURRENT_PRICE_STATUS = "current"
EXPECTED_CURRENCY = "CNY"
EXPECTED_UNIT = "GPU_HOUR"
_MIN_REFRESH_INTERVAL_MS = 30_000
_MAX_REFRESH_INTERVAL_MS = 600_000


class KaiPricingError(RuntimeError):
    """An upstream failure reduced to a stable, non-sensitive error code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class KaiPriceBatch:
    quotes: tuple[dict[str, Any], ...]
    observed_at: datetime
    valid_until: datetime
    data_version: int
    refresh_interval_ms: int
    raw_count: int


@dataclass(frozen=True)
class KaiCandleSeries:
    """A strictly validated official series and its real temporal coverage."""

    candles: tuple[dict[str, Any], ...]
    coverage_class: str
    coverage_span_seconds: float


_T = TypeVar("_T")


class _SingleFlightTtlCache:
    """Tiny bounded cache that coalesces concurrent requests for one key."""

    def __init__(self, max_entries: int = 128):
        self.max_entries = max_entries
        self._condition = Condition()
        self._entries: dict[tuple, tuple[float, object]] = {}
        self._inflight: set[tuple] = set()

    def get_or_load(
        self,
        key: tuple,
        ttl_seconds: float | Callable[[_T], float],
        loader: Callable[[], _T],
        *,
        deadline: float | None = None,
    ) -> _T:
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise KaiPricingError("upstream_timeout")
            with self._condition:
                cached = self._entries.get(key)
                if cached and cached[0] > now:
                    return cached[1]  # type: ignore[return-value]
                if key not in self._inflight:
                    self._inflight.add(key)
                    break
                wait_seconds = 0.5
                if deadline is not None:
                    wait_seconds = min(wait_seconds, max(deadline - now, 0.01))
                self._condition.wait(timeout=wait_seconds)
        try:
            value = loader()
        except Exception:
            with self._condition:
                self._inflight.discard(key)
                self._condition.notify_all()
            raise
        with self._condition:
            if len(self._entries) >= self.max_entries:
                expired = [item_key for item_key, item in self._entries.items() if item[0] <= time.monotonic()]
                for item_key in expired:
                    self._entries.pop(item_key, None)
                while len(self._entries) >= self.max_entries:
                    self._entries.pop(next(iter(self._entries)))
            resolved_ttl = ttl_seconds(value) if callable(ttl_seconds) else ttl_seconds
            self._entries[key] = (time.monotonic() + max(float(resolved_ttl), 0.1), value)
            self._inflight.discard(key)
            self._condition.notify_all()
        return value

    def clear(self) -> None:
        with self._condition:
            self._entries.clear()
            self._condition.notify_all()


_PRICE_CACHE = _SingleFlightTtlCache(max_entries=64)
_CANDLE_CACHE = _SingleFlightTtlCache(max_entries=128)
_CANDLE_WORKERS = max(1, int(settings.KAI_CANDLE_MAX_WORKERS))
_CANDLE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_CANDLE_WORKERS,
    thread_name_prefix="kai-candle",
)
atexit.register(_CANDLE_EXECUTOR.shutdown, wait=False, cancel_futures=True)


class _AsyncHttpRunner:
    """One bounded async transport enforcing a true end-to-end deadline.

    httpx's scalar timeout is a per-phase inactivity timeout.  A response can
    therefore spend almost that amount in connect, first-byte and multiple
    reads.  This dedicated event loop wraps the whole request in one asyncio
    timeout, while the synchronous caller also waits only until the same
    absolute deadline.  Cancellation exits the response context and releases
    the connection instead of leaving an unbounded executor backlog.
    """

    def __init__(self, max_pending: int):
        self.max_pending = max(1, int(max_pending))
        self._slots = BoundedSemaphore(self.max_pending)
        self._state_lock = Lock()
        self._pending = 0
        self._peak_pending = 0
        self._active = 0
        self._peak_active = 0
        self._ready = Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: httpx.AsyncClient | None = None
        self._startup_error: BaseException | None = None
        self._thread = Thread(target=self._run, name="kai-http-loop", daemon=True)
        self._thread.start()
        # Loading the platform CA bundle can be noticeably slow on a cold
        # Windows process.  This happens once at module start and must not be
        # confused with an upstream request deadline.
        if not self._ready.wait(timeout=15) or self._startup_error:
            raise RuntimeError("failed to initialize KAI HTTP transport") from self._startup_error

    @property
    def pending_count(self) -> int:
        with self._state_lock:
            return self._pending

    @property
    def peak_pending(self) -> int:
        with self._state_lock:
            return self._peak_pending

    @property
    def active_count(self) -> int:
        """Number of request coroutines that have actually entered the loop."""

        with self._state_lock:
            return self._active

    @property
    def peak_active(self) -> int:
        with self._state_lock:
            return self._peak_active

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                headers={"Accept": "application/json", "User-Agent": "WOD-KAI-Pricing/1.0"},
                limits=httpx.Limits(
                    max_connections=self.max_pending,
                    max_keepalive_connections=self.max_pending,
                    keepalive_expiry=300,
                ),
            )
        except BaseException as exc:  # startup must fail closed
            self._startup_error = exc
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            if self._client is not None:
                loop.run_until_complete(self._client.aclose())
            loop.close()

    async def _request(self, url: str, max_bytes: int, total_timeout: float) -> tuple[dict[str, Any], int]:
        if self._client is None:
            raise KaiPricingError("upstream_error")
        content = bytearray()
        try:
            async with asyncio.timeout(total_timeout):
                timeout = httpx.Timeout(max(total_timeout, 0.1))
                async with self._client.stream("GET", url, timeout=timeout) as response:
                    if response.status_code >= 400:
                        raise _safe_http_error(response)
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise KaiPricingError("upstream_response_too_large")
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise KaiPricingError("upstream_response_too_large")
                payload = httpx.Response(200, content=bytes(content)).json()
        except KaiPricingError:
            raise
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise KaiPricingError("upstream_timeout") from exc
        except httpx.HTTPError as exc:
            raise KaiPricingError("upstream_error") from exc
        except ValueError as exc:
            raise KaiPricingError("upstream_invalid_response") from exc
        if not isinstance(payload, dict):
            raise KaiPricingError("upstream_invalid_response")
        return payload, len(content)

    async def _request_and_release(
        self,
        url: str,
        max_bytes: int,
        total_timeout: float,
        admission: dict[str, bool],
    ) -> tuple[dict[str, Any], int]:
        """Keep the admission slot until cancellation has really unwound.

        Releasing from the ``concurrent.futures.Future`` callback is subtly
        unsafe: cancelling that proxy can mark it done before the event-loop
        task has left the response context.  The next caller could then start
        another real request and exceed the transport bound.  This coroutine's
        ``finally`` executes only after the async request (including response
        close) has completed or acknowledged cancellation.
        """

        with self._state_lock:
            # A proxy future can be cancelled before this coroutine receives
            # its first event-loop turn.  In that case the done callback below
            # has already returned the slot and this coroutine must not start
            # any network I/O.
            if admission["released"]:
                raise asyncio.CancelledError
            admission["started"] = True
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)
        try:
            return await self._request(url, max_bytes, total_timeout)
        finally:
            release_slot = False
            with self._state_lock:
                self._active -= 1
                if not admission["released"]:
                    admission["released"] = True
                    self._pending -= 1
                    release_slot = True
            if release_slot:
                self._slots.release()

    def request(self, url: str, max_bytes: int, deadline: float) -> tuple[dict[str, Any], int]:
        remaining = deadline - time.monotonic()
        if remaining < 0.1 or not self._slots.acquire(timeout=max(remaining, 0)):
            raise KaiPricingError("upstream_timeout")
        with self._state_lock:
            self._pending += 1
            self._peak_pending = max(self._peak_pending, self._pending)
        loop = self._loop
        if loop is None or not loop.is_running():
            with self._state_lock:
                self._pending -= 1
            self._slots.release()
            raise KaiPricingError("upstream_error")
        remaining = deadline - time.monotonic()
        if remaining < 0.1:
            with self._state_lock:
                self._pending -= 1
            self._slots.release()
            raise KaiPricingError("upstream_timeout")
        admission = {"started": False, "released": False}
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._request_and_release(url, max_bytes, remaining, admission), loop,
            )
        except Exception:
            with self._state_lock:
                self._pending -= 1
            self._slots.release()
            raise KaiPricingError("upstream_error")

        def release_if_never_started(_future) -> None:
            release_slot = False
            with self._state_lock:
                if not admission["started"] and not admission["released"]:
                    admission["released"] = True
                    self._pending -= 1
                    release_slot = True
            if release_slot:
                self._slots.release()

        future.add_done_callback(release_if_never_started)

        try:
            return future.result(timeout=max(deadline - time.monotonic(), 0))
        except FutureTimeoutError as exc:
            future.cancel()
            raise KaiPricingError("upstream_timeout") from exc

    def close(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
            self._thread.join(timeout=2)


_HTTP_RUNNER = _AsyncHttpRunner(max_pending=max(_CANDLE_WORKERS + 2, 6))
atexit.register(_HTTP_RUNNER.close)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise KaiPricingError("upstream_invalid_response")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KaiPricingError("upstream_invalid_response") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _safe_http_error(response: httpx.Response) -> KaiPricingError:
    if response.status_code == 429:
        return KaiPricingError("rate_limited")
    if response.status_code in (401, 403):
        return KaiPricingError("authentication_failed")
    return KaiPricingError("upstream_error")


def _get_json(
    path: str,
    *,
    timeout: float,
    max_bytes: int,
    deadline: float | None = None,
) -> tuple[dict[str, Any], int]:
    url = f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    absolute_deadline = deadline or (time.monotonic() + max(float(timeout), 0.1))
    # Never start a request that cannot receive even the transport's minimum
    # scheduling budget.  The async runner enforces this deadline across all
    # network phases, not once per phase.
    if absolute_deadline - time.monotonic() < 0.1:
        raise KaiPricingError("upstream_timeout")
    return _HTTP_RUNNER.request(url, max_bytes, absolute_deadline)


def _load_price_batch(
    *,
    gpu_models: tuple[str, ...] = (),
    product_ids: tuple[str, ...] = (),
    deadline: float | None = None,
) -> KaiPriceBatch:
    params = [*(('gpuModel', value) for value in gpu_models), *(('productId', value) for value in product_ids)]
    path = "/v1/prices"
    if params:
        path = f"{path}?{urlencode(params)}"
    payload, _ = _get_json(
        path,
        timeout=settings.KAI_PRICING_HTTP_TIMEOUT,
        max_bytes=settings.KAI_PRICING_MAX_RESPONSE_BYTES,
        deadline=deadline,
    )
    rows = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(rows, list) or not isinstance(meta, dict):
        raise KaiPricingError("upstream_invalid_response")
    observed_at = _parse_datetime(meta.get("asOf"))
    valid_until = _parse_datetime(meta.get("validUntil"))
    try:
        raw_count = int(meta.get("count"))
        data_version = int(meta.get("dataVersion"))
    except (TypeError, ValueError) as exc:
        raise KaiPricingError("upstream_invalid_response") from exc

    # KAI v24 no longer publishes ``refreshIntervalMs``.  Its validity window
    # remains authoritative, so derive the interval only when it is an exact,
    # plausible number of milliseconds.  If the legacy field is present, keep
    # validating it and require it to agree with that same window.
    window_microseconds = (valid_until - observed_at) // timedelta(microseconds=1)
    if window_microseconds % 1000:
        raise KaiPricingError("upstream_invalid_response")
    window_ms = window_microseconds // 1000
    if "refreshIntervalMs" not in meta:
        refresh_ms = window_ms
    else:
        refresh_value = meta.get("refreshIntervalMs")
        try:
            refresh_decimal = Decimal(str(refresh_value))
            refresh_ms = int(refresh_decimal)
        except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
            raise KaiPricingError("upstream_invalid_response") from exc
        if not refresh_decimal.is_finite() or refresh_decimal != refresh_ms:
            raise KaiPricingError("upstream_invalid_response")
    if (
        raw_count != len(rows)
        or data_version < 1
        or valid_until <= observed_at
        or not _MIN_REFRESH_INTERVAL_MS <= window_ms <= _MAX_REFRESH_INTERVAL_MS
        or not _MIN_REFRESH_INTERVAL_MS <= refresh_ms <= _MAX_REFRESH_INTERVAL_MS
        or refresh_ms != window_ms
    ):
        raise KaiPricingError("upstream_invalid_response")
    # One publication interval of clock-skew tolerance is sufficient.  Older
    # batches remain in the database but must not be advertised as current.
    grace_seconds = max(min(refresh_ms / 1000, 600), 30)
    if utcnow() > valid_until + timedelta(seconds=grace_seconds):
        raise KaiPricingError("upstream_stale")
    seen_product_ids: set[str] = set()
    validated_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise KaiPricingError("upstream_invalid_response")
        product_id = str(row.get("productId") or "").strip()
        row_id = str(row.get("id") or "").strip()
        try:
            row_as_of = _parse_datetime(row.get("asOf"))
            row_version = int(row.get("dataVersion"))
        except (TypeError, ValueError, KaiPricingError) as exc:
            raise KaiPricingError("upstream_invalid_response") from exc
        if (
            not product_id
            or row_id != product_id
            or product_id in seen_product_ids
            or row_as_of != observed_at
            or row_version != data_version
        ):
            raise KaiPricingError("upstream_invalid_response")
        seen_product_ids.add(product_id)
        validated_rows.append(row)
    return KaiPriceBatch(
        quotes=tuple(validated_rows),
        observed_at=observed_at,
        valid_until=valid_until,
        data_version=data_version,
        refresh_interval_ms=refresh_ms,
        raw_count=raw_count,
    )


def fetch_price_batch(
    *,
    use_cache: bool = True,
    gpu_models: Iterable[str] = (),
    product_ids: Iterable[str] = (),
    deadline: float | None = None,
) -> KaiPriceBatch:
    """Return one validated KAI publication batch.

    KAI publishes atomically every five minutes.  A short cache lets the market
    and product schedulers share the same immutable batch without changing its
    source timestamp.
    """

    model_filters = tuple(sorted({str(value).strip() for value in gpu_models if str(value).strip()}))
    product_filters = tuple(sorted({str(value).strip() for value in product_ids if str(value).strip()}))
    loader = lambda: _load_price_batch(
        gpu_models=model_filters,
        product_ids=product_filters,
        deadline=deadline,
    )
    if not use_cache:
        return loader()
    def cache_ttl(batch: KaiPriceBatch) -> float:
        until_next_publication = (batch.valid_until - utcnow()).total_seconds()
        published_interval = max(batch.refresh_interval_ms / 1000, 1)
        return max(min(until_next_publication, published_interval), 1)

    return _PRICE_CACHE.get_or_load(
        ("prices", model_filters, product_filters),
        cache_ttl,
        loader,
        deadline=deadline,
    )


def normalized_current_quotes(batch: KaiPriceBatch) -> list[dict[str, Any]]:
    """Map only explicit current GPU-hour quotes; reject, never guess, fields."""

    result: list[dict[str, Any]] = []
    for raw in batch.quotes:
        availability = raw.get("availability")
        if raw.get("priceStatus") != CURRENT_PRICE_STATUS:
            continue
        if not isinstance(availability, dict) or availability.get("status") != "available":
            continue
        if raw.get("currency") != EXPECTED_CURRENCY or raw.get("unit") != EXPECTED_UNIT:
            continue
        price = _positive_decimal(raw.get("priceCny"))
        model = canonicalize_gpu(raw.get("gpuName")) or canonicalize_gpu(raw.get("gpuModel"))
        variant = normalize_gpu_variant(model, memory_variant_from_text(raw.get("vram"))) if model else ""
        product_id = str(raw.get("productId") or raw.get("id") or "").strip()
        region = str(raw.get("region") or "").strip()
        if not price or not model or not variant or not product_id or not region:
            continue
        quantities: list[int] = []
        for value in raw.get("gpuCountOptions") or []:
            try:
                quantity = int(value)
            except (TypeError, ValueError):
                continue
            if quantity > 0:
                quantities.append(quantity)
        result.append({
            "external_product_id": product_id,
            "gpu_model": model,
            "gpu_variant": variant,
            "gpu_name": str(raw.get("gpuName") or model),
            "display_name": str(raw.get("gpuModel") or f"{model} {variant}"),
            "region": region,
            "form_factor": str(raw.get("formFactor") or ""),
            "price_cny": price,
            "billing_mode": "ondemand",
            "max_configurable_quantity": max(quantities) if quantities else None,
            "gpu_count_options": tuple(sorted(set(quantities))),
            "observed_at": batch.observed_at,
            "data_version": batch.data_version,
        })
    return result


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise KaiPricingError("history_unavailable")
    middle = len(ordered) // 2
    return (
        (ordered[middle - 1] + ordered[middle]) / Decimal("2")
        if len(ordered) % 2 == 0
        else ordered[middle]
    )


def _without_outliers(values: list[Decimal]) -> list[Decimal]:
    if len(values) < 4:
        return values
    ordered = sorted(values)

    def percentile(ratio: Decimal) -> Decimal:
        position = Decimal(len(ordered) - 1) * ratio
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - Decimal(lower)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    q1 = percentile(Decimal("0.25"))
    q3 = percentile(Decimal("0.75"))
    spread = q3 - q1
    lower = q1 - spread * Decimal("1.5")
    upper = q3 + spread * Decimal("1.5")
    accepted = [value for value in values if lower <= value <= upper]
    return accepted or values


_RANGE_CONFIG = {
    "1h": (timedelta(hours=1), "1h", 3600, 1),
    "6h": (timedelta(hours=6), "1h", 3600, 1),
    "24h": (timedelta(hours=24), "1h", 3600, 1),
    # Seven days always comes from KAI's official historical 4-hour OHLC.
    "7d": (timedelta(days=7), "4h", 4 * 3600, 1),
    "30d": (timedelta(days=30), "1d", 24 * 3600, 1),
    "90d": (timedelta(days=90), "1d", 24 * 3600, 3),
}


# KAI's ``gpuModel`` filter is exact.  These are observed public display names
# whose vendor/generation token is intentionally removed by WOD's canonical
# identity.  Keep this table explicit: guessing aliases risks mixing SKUs.
_KAI_GPU_MODEL_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("H100", "94GB"): ("H100 NVL 94GB",),
    ("L40S", "45GB"): ("L40S 44.7GB",),
    ("RTX2000", "16GB"): ("RTX 2000 Ada 16GB",),
    ("RTX4000", "20GB"): ("RTX 4000 Ada 20GB",),
    ("RTX4000", "24GB"): ("RTX PRO 4000 Blackwell 24GB",),
    ("RTX4070SUPER", "16GB"): ("RTX 4070 SUPER Ti 16GB",),
    ("RTX4500", "24GB"): ("RTX 4500 Ada 24GB",),
    ("RTX4500", "32GB"): ("RTX PRO 4500 Blackwell 32GB",),
    ("RTX5000", "32GB"): ("RTX 5000 Ada 32GB",),
    ("RTX5000", "48GB"): ("RTX PRO 5000 48GB",),
    ("RTX5880", "48GB"): ("RTX 5880 Ada 48GB",),
    ("RTX6000", "24GB"): ("Quadro RTX 6000 24GB",),
    ("RTX6000", "48GB"): ("RTX 6000 Ada 48GB",),
}


def _upstream_gpu_model_filters(model: str, variant: str) -> tuple[str, ...]:
    """Return bounded exact KAI ``gpuModel`` values for one canonical SKU.

    KAI's filter is exact.  WOD intentionally keeps only a small documented
    alias set for canonical names that discard a vendor/display token; every
    returned row is still normalized and checked against ``model``/``variant``
    before it can become a candidate.
    """

    canonical_model = canonicalize_gpu(model) or str(model or "").strip().upper()
    canonical_variant = normalize_gpu_variant(canonical_model, variant)
    if not canonical_model or not canonical_variant:
        return ()
    names: set[str] = {f"{canonical_model} {canonical_variant}"}
    rtx = re.fullmatch(r"RTX(\d{4})(TI|SUPER|D)?", canonical_model)
    if rtx:
        suffix = {"TI": " Ti", "SUPER": " SUPER", "D": "D", None: ""}[rtx.group(2)]
        names.add(f"RTX {rtx.group(1)}{suffix} {canonical_variant}")
        # The upstream currently publishes both word orders for this SKU.
        if rtx.group(2) == "TI":
            names.add(f"RTX {rtx.group(1)} Ti Super {canonical_variant}")
            names.add(f"RTX {rtx.group(1)} SUPER Ti {canonical_variant}")
    if canonical_model in {"A4000", "A5000", "A6000"}:
        names.add(f"RTX {canonical_model} {canonical_variant}")
    if canonical_model == "RTXPRO6000":
        names.update({
            f"RTX PRO 6000 Blackwell {canonical_variant}",
            f"RTX PRO 6000 SE {canonical_variant}",
            f"RTX PRO 6000D {canonical_variant}",
        })
    names.update(_KAI_GPU_MODEL_ALIASES.get((canonical_model, canonical_variant), ()))
    return tuple(sorted(names))


def _fetch_product_candles(
    product_id: str,
    interval: str,
    months: int = 1,
    *,
    deadline: float | None = None,
) -> tuple[dict[str, Any], int]:
    encoded = quote(product_id, safe="")
    return _get_json(
        f"/v1/prices/{encoded}/candles?months={max(1, int(months))}&interval={interval}",
        timeout=settings.KAI_CANDLE_HTTP_TIMEOUT,
        max_bytes=settings.KAI_CANDLE_MAX_RESPONSE_BYTES,
        deadline=deadline,
    )


def _parse_complete_candle_series(
    payload: dict[str, Any],
    *,
    product_id: str,
    since: datetime,
    until: datetime,
    interval_seconds: int,
    expected_interval: str,
    expected_months: int = 1,
) -> KaiCandleSeries | None:
    data = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict):
        return None
    if str(data.get("productId") or "") != product_id:
        return None
    if data.get("currency") != EXPECTED_CURRENCY or data.get("unit") != EXPECTED_UNIT:
        return None
    if data.get("interval") != expected_interval or meta.get("interval") != expected_interval:
        return None
    try:
        data_months = int(data.get("months"))
        meta_months = int(meta.get("months"))
        meta_interval_ms = int(meta.get("intervalMs"))
        data_version = int(meta.get("dataVersion"))
        response_count = int(meta.get("count"))
        meta_as_of = _parse_datetime(meta.get("asOf"))
        meta_from = _parse_datetime(meta.get("from"))
        meta_to = _parse_datetime(meta.get("to"))
    except (TypeError, ValueError, KaiPricingError):
        return None
    if (
        data_months != expected_months
        or meta_months != expected_months
        or meta_interval_ms != interval_seconds * 1000
        or data_version < 1
        or meta_from >= meta_to
        or meta_to > meta_as_of + timedelta(seconds=interval_seconds * 2)
        or meta_to < since - timedelta(seconds=interval_seconds)
    ):
        return None
    raw_candles = data.get("candles")
    if not isinstance(raw_candles, list) or response_count != len(raw_candles):
        return None
    parsed: list[dict[str, Any]] = []
    for raw in raw_candles:
        if not isinstance(raw, dict):
            return None
        try:
            observed = _parse_datetime(raw.get("asOf"))
        except KaiPricingError:
            return None
        if observed < since - timedelta(seconds=interval_seconds) or observed > until + timedelta(seconds=interval_seconds):
            continue
        values = {name: _positive_decimal(raw.get(name)) for name in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            return None
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            return None
        parsed.append({"observed_at": observed, **values})
    parsed.sort(key=lambda item: item["observed_at"])
    if not parsed:
        return None
    observed_times = [item["observed_at"] for item in parsed]
    if len(set(observed_times)) != len(observed_times):
        return None
    if any(
        int((current - previous).total_seconds()) != interval_seconds
        for previous, current in zip(observed_times, observed_times[1:])
    ):
        return None
    coverage = (parsed[-1]["observed_at"] - parsed[0]["observed_at"]).total_seconds()
    required = max((until - since).total_seconds(), 0)
    coverage_class = (
        "single" if len(parsed) == 1
        else "full" if coverage >= required
        else "partial"
    )
    return KaiCandleSeries(tuple(parsed), coverage_class, coverage)


def _coverage_contract(coverage_class: str) -> dict[str, str]:
    if coverage_class == "full":
        return {
            "history_status": "available",
            "curve_status": "full",
            "history_coverage_status": "complete",
            "data_quality": "official_historical_ohlc",
            "coverage_quality": "verified",
        }
    if coverage_class == "partial":
        return {
            "history_status": "partial_history",
            "curve_status": "partial",
            "history_coverage_status": "partial",
            "data_quality": "official_historical_ohlc_partial",
            "coverage_quality": "partial",
        }
    return {
        "history_status": "single_observation",
        "curve_status": "single",
        "history_coverage_status": "single",
        "data_quality": "official_historical_ohlc_single",
        "coverage_quality": "single_observation",
    }


def _aggregate_kai_candles(
    model: str,
    variant: str,
    range_name: str,
    *,
    deadline: float,
) -> dict[str, Any]:
    if range_name not in _RANGE_CONFIG:
        raise KaiPricingError("unsupported_range")
    duration, interval, interval_seconds, months = _RANGE_CONFIG[range_name]
    filters = _upstream_gpu_model_filters(model, variant)
    if not filters:
        raise KaiPricingError("history_unavailable")
    batch = fetch_price_batch(gpu_models=filters, deadline=deadline)
    if time.monotonic() >= deadline:
        raise KaiPricingError("upstream_timeout")
    quotes = [
        item for item in normalized_current_quotes(batch)
        if item["gpu_model"] == model and item["gpu_variant"] == variant
    ]
    candidates = sorted(quotes, key=lambda item: item["external_product_id"])
    candidates = candidates[:max(1, int(settings.KAI_CANDLE_MAX_PRODUCTS))]
    if not candidates:
        raise KaiPricingError("history_unavailable")

    until = batch.observed_at
    since = until - duration
    futures = {
        _CANDLE_EXECUTOR.submit(
            _fetch_product_candles,
            item["external_product_id"],
            interval,
            months,
            deadline=deadline,
        ): item
        for item in candidates
    }
    selected: list[tuple[dict[str, Any], KaiCandleSeries]] = []
    total_bytes = 0
    done, pending = wait(futures, timeout=max(deadline - time.monotonic(), 0))

    def consume(done_futures: Iterable) -> None:
        nonlocal total_bytes
        for future in sorted(done_futures, key=lambda item: futures[item]["external_product_id"]):
            candidate = futures[future]
            try:
                payload, response_bytes = future.result()
            except Exception:  # one incomplete region must not poison other real series
                continue
            total_bytes += response_bytes
            if total_bytes > int(settings.KAI_CANDLE_MAX_TOTAL_BYTES):
                raise KaiPricingError("upstream_response_too_large")
            series = _parse_complete_candle_series(
                payload,
                product_id=candidate["external_product_id"],
                since=since,
                until=until,
                interval_seconds=interval_seconds,
                expected_interval=interval,
                expected_months=months,
            )
            if series:
                selected.append((candidate, series))

    # The candidate set is fixed and sorted.  Under normal operation all N
    # complete before the absolute deadline, so response race order can never
    # change the aggregate.  On a partial upstream timeout, accept only the
    # deterministic sorted subset that actually completed; a single slow
    # region therefore cannot erase other complete official histories.
    consume(done)
    for future in pending:
        future.cancel()
    if not selected:
        if time.monotonic() >= deadline:
            raise KaiPricingError("upstream_timeout")
        raise KaiPricingError("history_unavailable")

    by_time: dict[datetime, list[dict[str, Decimal]]] = defaultdict(list)
    for _, series in selected:
        for candle in series.candles:
            if since - timedelta(seconds=interval_seconds) <= candle["observed_at"] <= until:
                by_time[candle["observed_at"]].append(candle)

    # Multiple regions can expose different real retention windows.  Keep one
    # deterministic, strictly consecutive window rather than returning a
    # visually connected series across a temporal gap.
    consecutive_windows: list[list[tuple[datetime, list[dict[str, Decimal]]]]] = []
    for observed_at, rows in sorted(by_time.items()):
        if (
            not consecutive_windows
            or int((observed_at - consecutive_windows[-1][-1][0]).total_seconds()) != interval_seconds
        ):
            consecutive_windows.append([])
        consecutive_windows[-1].append((observed_at, rows))
    selected_window = max(
        consecutive_windows,
        key=lambda window: (len(window), window[-1][0]),
        default=[],
    )
    candles: list[dict[str, Any]] = []
    for observed_at, rows in selected_window:
        aggregated: dict[str, Decimal] = {}
        for name in ("open", "high", "low", "close"):
            aggregated[name] = _median(_without_outliers([Decimal(row[name]) for row in rows]))
        high = max(aggregated["high"], aggregated["open"], aggregated["close"])
        low = min(aggregated["low"], aggregated["open"], aggregated["close"])
        candles.append({
            "start_time": observed_at.isoformat(timespec="seconds") + "Z",
            "end_time": (observed_at + timedelta(seconds=interval_seconds)).isoformat(timespec="seconds") + "Z",
            "open_price_cny": float(aggregated["open"]),
            "high_price_cny": float(high),
            "low_price_cny": float(low),
            "close_price_cny": float(aggregated["close"]),
            "sample_count": len(rows),
            "observation_count": len(rows),
            "sources": [SOURCE_KEY],
        })
    if not candles:
        raise KaiPricingError("history_unavailable")

    latest_prices = [Decimal(item["price_cny"]) for item, _ in selected]
    first_time = _parse_datetime(candles[0]["start_time"])
    last_time = _parse_datetime(candles[-1]["start_time"])
    coverage_span_seconds = (last_time - first_time).total_seconds()
    coverage_class = (
        "single" if len(candles) == 1
        else "full" if coverage_span_seconds >= duration.total_seconds()
        else "partial"
    )
    coverage = _coverage_contract(coverage_class)
    selected_ids = [item["external_product_id"] for item, _ in selected]
    return {
        "gpu_model": model,
        "gpu_variant": variant,
        "range": range_name,
        "bucket_seconds": interval_seconds,
        "tick_seconds": interval_seconds,
        "method": "kai_official_ohlc_cross_region_robust_median",
        "is_interpolated": False,
        "selected_source": SOURCE_KEY,
        "history_status": coverage["history_status"],
        "curve_status": coverage["curve_status"],
        "coverage_class": coverage_class,
        "history_coverage_status": coverage["history_coverage_status"],
        "coverage_day_count": len({item["start_time"][:10] for item in candles}),
        "coverage_span_hours": round(coverage_span_seconds / 3600, 1),
        "data_quality": coverage["data_quality"],
        "provenance": {
            "kind": "official_historical_ohlc_aggregate",
            "dataset_source": "kai_pricing_api",
            "upstream_provider": SOURCE_KEY,
            "source_url": f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/v1/prices/{{productId}}/candles",
            "license": None,
            "terms_status": "not_declared_by_public_response",
            "data_version": batch.data_version,
            "as_of": batch.observed_at.isoformat(timespec="seconds") + "Z",
            "product_selection": "lexicographic_product_id_current_strict_series",
            "current_quote_filter": "exact_gpuModel_query",
            "candidate_product_count": len(candidates),
            "selected_product_count": len(selected_ids),
            "selected_product_ids": selected_ids,
            "selection_completeness": (
                "full" if len(selected_ids) == len(candidates) else "partial_before_deadline"
            ),
            "max_products": int(settings.KAI_CANDLE_MAX_PRODUCTS),
            "aggregation": "per_timestamp_iqr_filtered_median_for_each_ohlc_field",
            "interval": interval,
            "cache_seconds": int(settings.KAI_CANDLE_CACHE_SECONDS),
            "live_component_included": False,
            "coverage_quality": coverage["coverage_quality"],
        },
        "latest_live_price_cny": float(_median(latest_prices)),
        "latest_live_observed_at": batch.observed_at.isoformat(timespec="seconds") + "Z",
        "latest_live_comparable_to_history": True,
        "candles": candles,
    }


def get_aggregated_candles(model: str, variant: str, range_name: str) -> dict[str, Any]:
    canonical_model = canonicalize_gpu(model) or model
    canonical_variant = normalize_gpu_variant(canonical_model, variant)
    key = ("candles", canonical_model, canonical_variant, range_name)
    deadline = time.monotonic() + max(float(settings.KAI_CANDLE_TOTAL_TIMEOUT), 0.1)
    return _CANDLE_CACHE.get_or_load(
        key,
        max(int(settings.KAI_CANDLE_CACHE_SECONDS), 1),
        lambda: _aggregate_kai_candles(
            canonical_model,
            canonical_variant,
            range_name,
            deadline=deadline,
        ),
        deadline=deadline,
    )


def _load_exact_product_candles(
    external_product_id: str,
    model: str,
    variant: str,
    range_name: str,
    *,
    deadline: float,
) -> dict[str, Any]:
    if range_name not in _RANGE_CONFIG:
        raise KaiPricingError("unsupported_range")
    product_id = str(external_product_id or "").strip()
    if not product_id or len(product_id) > 160:
        raise KaiPricingError("product_not_found")
    canonical_model = canonicalize_gpu(model) or model
    canonical_variant = normalize_gpu_variant(canonical_model, variant)
    duration, interval, interval_seconds, months = _RANGE_CONFIG[range_name]
    batch = fetch_price_batch(product_ids=(product_id,), deadline=deadline)
    if time.monotonic() >= deadline:
        raise KaiPricingError("upstream_timeout")
    current = {
        item["external_product_id"]: item
        for item in normalized_current_quotes(batch)
    }
    product = current.get(product_id)
    if not product:
        raise KaiPricingError("product_not_found")
    if (product["gpu_model"], product["gpu_variant"]) != (canonical_model, canonical_variant):
        raise KaiPricingError("product_identity_mismatch")

    payload, _ = _fetch_product_candles(product_id, interval, months, deadline=deadline)
    since = batch.observed_at - duration
    series = _parse_complete_candle_series(
        payload,
        product_id=product_id,
        since=since,
        until=batch.observed_at,
        interval_seconds=interval_seconds,
        expected_interval=interval,
        expected_months=months,
    )
    if not series:
        raise KaiPricingError("history_unavailable")
    candles = [{
        "start_time": item["observed_at"].isoformat(timespec="seconds") + "Z",
        "end_time": (item["observed_at"] + timedelta(seconds=interval_seconds)).isoformat(timespec="seconds") + "Z",
        "open_price_cny": float(item["open"]),
        "high_price_cny": float(item["high"]),
        "low_price_cny": float(item["low"]),
        "close_price_cny": float(item["close"]),
        "sample_count": 1,
        "observation_count": 1,
        "sources": [SOURCE_KEY],
    } for item in series.candles]
    first_time = series.candles[0]["observed_at"]
    last_time = series.candles[-1]["observed_at"]
    coverage = _coverage_contract(series.coverage_class)
    return {
        "gpu_model": canonical_model,
        "gpu_variant": canonical_variant,
        "external_product_id": product_id,
        "range": range_name,
        "bucket_seconds": interval_seconds,
        "tick_seconds": interval_seconds,
        "method": "kai_official_exact_product_ohlc",
        "is_interpolated": False,
        "selected_source": SOURCE_KEY,
        "history_status": coverage["history_status"],
        "curve_status": coverage["curve_status"],
        "coverage_class": series.coverage_class,
        "history_coverage_status": coverage["history_coverage_status"],
        "coverage_day_count": len({item["observed_at"].date() for item in series.candles}),
        "coverage_span_hours": round(series.coverage_span_seconds / 3600, 1),
        "data_quality": coverage["data_quality"],
        "provenance": {
            "kind": "official_historical_ohlc_exact_product",
            "dataset_source": "kai_pricing_api",
            "upstream_provider": SOURCE_KEY,
            "source_url": f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/v1/prices/{{productId}}/candles",
            "license": None,
            "terms_status": "not_declared_by_public_response",
            "data_version": batch.data_version,
            "as_of": batch.observed_at.isoformat(timespec="seconds") + "Z",
            "product_selection": "exact_product_id",
            "selected_product_id": product_id,
            "aggregation": "none_exact_product_ohlc",
            "interval": interval,
            "cache_seconds": int(settings.KAI_CANDLE_CACHE_SECONDS),
            "live_component_included": False,
            "coverage_quality": coverage["coverage_quality"],
        },
        "latest_live_price_cny": float(product["price_cny"]),
        "latest_live_observed_at": batch.observed_at.isoformat(timespec="seconds") + "Z",
        "latest_live_comparable_to_history": True,
        "candles": candles,
    }


def get_exact_product_candles(
    external_product_id: str,
    model: str,
    variant: str,
    range_name: str,
) -> dict[str, Any]:
    canonical_model = canonicalize_gpu(model) or model
    canonical_variant = normalize_gpu_variant(canonical_model, variant)
    product_id = str(external_product_id or "").strip()
    key = ("exact_candles", product_id, canonical_model, canonical_variant, range_name)
    deadline = time.monotonic() + max(float(settings.KAI_CANDLE_TOTAL_TIMEOUT), 0.1)
    return _CANDLE_CACHE.get_or_load(
        key,
        max(int(settings.KAI_CANDLE_CACHE_SECONDS), 1),
        lambda: _load_exact_product_candles(
            product_id,
            canonical_model,
            canonical_variant,
            range_name,
            deadline=deadline,
        ),
        deadline=deadline,
    )


def _load_ranking_metrics(
    identities: tuple[tuple[str, str], ...],
    *,
    deadline: float,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Build bounded seven-day metrics from official KAI OHLC history.

    Ranking is a bulk request, so it selects at most one deterministic current
    product per identity and at most ``KAI_RANKING_MAX_PRODUCTS`` products in
    total.  This prevents an N-model × N-region request fan-out while keeping
    every published number backed by an official historical candle.
    """

    requested_identities = identities[:max(1, int(settings.KAI_RANKING_MAX_PRODUCTS))]
    requested = set(requested_identities)
    if not requested:
        return {}
    model_filters = tuple(sorted({
        upstream_model
        for model, variant in requested_identities
        for upstream_model in _upstream_gpu_model_filters(model, variant)
    }))
    if not model_filters:
        return {}
    batch = fetch_price_batch(gpu_models=model_filters, deadline=deadline)
    if time.monotonic() >= deadline:
        raise KaiPricingError("upstream_timeout")
    by_identity: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in normalized_current_quotes(batch):
        identity = (item["gpu_model"], item["gpu_variant"])
        if identity in requested:
            by_identity[identity].append(item)
    candidates = [
        sorted(items, key=lambda item: item["external_product_id"])[0]
        for identity, items in sorted(by_identity.items()) if items
    ][:max(1, int(settings.KAI_RANKING_MAX_PRODUCTS))]
    if not candidates:
        return {}

    duration, interval, interval_seconds, months = _RANGE_CONFIG["7d"]
    until = batch.observed_at
    since = until - duration
    futures = {
        _CANDLE_EXECUTOR.submit(
            _fetch_product_candles,
            item["external_product_id"],
            interval,
            months,
            deadline=deadline,
        ): item
        for item in candidates
    }
    remaining = max(deadline - time.monotonic(), 0)
    done, pending = wait(futures, timeout=remaining)
    for future in pending:
        future.cancel()

    total_bytes = 0
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for future in sorted(done, key=lambda item: futures[item]["external_product_id"]):
        candidate = futures[future]
        try:
            payload, response_bytes = future.result()
        except KaiPricingError:
            continue
        total_bytes += response_bytes
        if total_bytes > int(settings.KAI_CANDLE_MAX_TOTAL_BYTES):
            raise KaiPricingError("upstream_response_too_large")
        try:
            series = _parse_complete_candle_series(
                payload,
                product_id=candidate["external_product_id"],
                since=since,
                until=until,
                interval_seconds=interval_seconds,
                expected_interval=interval,
                expected_months=months,
            )
        except KaiPricingError:
            continue
        if not series:
            continue
        candles = series.candles
        lows = [Decimal(item["low"]) for item in candles]
        highs = [Decimal(item["high"]) for item in candles]
        closes = [Decimal(item["close"]) for item in candles]
        identity = (candidate["gpu_model"], candidate["gpu_variant"])
        # Short official series remain useful coverage evidence, but are never
        # promoted into a seven-day change/range/volatility claim.
        if series.coverage_class != "full":
            result[identity] = {
                "volatility_7d": None,
                "volatility_status": "insufficient_history",
                "volatility_quality": "limited_sample",
                "history_day_count": len({item["observed_at"].date() for item in candles}),
                "history_point_count": len(candles),
                "history_span_hours": round(series.coverage_span_seconds / 3600, 1),
                "history_min_daily_sample_count": 1,
                "history_bucket_count": len(candles),
                "history_coverage_status": series.coverage_class,
                "volatility_source_count": 1,
                "volatility_sources": [SOURCE_KEY],
                "volatility_billing_mode": "ondemand",
                "volatility_method": "official_ohlc_waiting_for_full_7d_window",
                "change_7d_pct": None,
                "range_low_cny": None,
                "range_high_cny": None,
                "observed_partial_low_cny": float(min(lows)),
                "observed_partial_high_cny": float(max(highs)),
                "flat_price_observed": min(lows) == max(highs),
                "history_provenance": {
                    "kind": "official_historical_ohlc_partial",
                    "dataset_source": "kai_pricing_api",
                    "upstream_provider": SOURCE_KEY,
                    "source_url": f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/v1/prices/{{productId}}/candles",
                    "license": None,
                    "terms_status": "not_declared_by_public_response",
                    "data_version": batch.data_version,
                    "as_of": batch.observed_at.isoformat(timespec="seconds") + "Z",
                    "selected_product_id": candidate["external_product_id"],
                    "interval": interval,
                    "live_component_included": False,
                    "coverage_quality": series.coverage_class,
                },
            }
            continue
        first_open = Decimal(candles[0]["open"])
        last_close = closes[-1]
        median_close = _median(_without_outliers(closes))
        range_pct = (
            float((max(highs) - min(lows)) / median_close * Decimal("100"))
            if median_close > 0 else None
        )
        change = (
            float((last_close / first_open - Decimal("1")) * Decimal("100"))
            if first_open > 0 else None
        )
        result[identity] = {
            "volatility_7d": round(range_pct, 2) if range_pct is not None else None,
            "volatility_status": "available",
            "volatility_quality": "verified",
            "history_day_count": len({item["observed_at"].date() for item in candles}),
            "history_point_count": len(candles),
            "history_span_hours": round(
                (candles[-1]["observed_at"] - candles[0]["observed_at"]).total_seconds() / 3600,
                1,
            ),
            "history_min_daily_sample_count": 1,
            "history_bucket_count": len(candles),
            "history_coverage_status": "complete",
            "volatility_source_count": 1,
            "volatility_sources": [SOURCE_KEY],
            "volatility_billing_mode": "ondemand",
            "volatility_method": "official_ohlc_high_low_range_over_median_close",
            "change_7d_pct": round(change, 2) if change is not None else None,
            "range_low_cny": float(min(lows)),
            "range_high_cny": float(max(highs)),
            "flat_price_observed": min(lows) == max(highs),
            "history_provenance": {
                "kind": "official_historical_ohlc",
                "dataset_source": "kai_pricing_api",
                "upstream_provider": SOURCE_KEY,
                "source_url": f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/v1/prices/{{productId}}/candles",
                "license": None,
                "terms_status": "not_declared_by_public_response",
                "data_version": batch.data_version,
                "as_of": batch.observed_at.isoformat(timespec="seconds") + "Z",
                "product_selection": "one_lexicographic_current_product_per_identity",
                "selected_product_id": candidate["external_product_id"],
                "global_product_cap": int(settings.KAI_RANKING_MAX_PRODUCTS),
                "interval": interval,
                "live_component_included": False,
                "coverage_quality": "verified",
            },
        }
    return result


def get_ranking_metrics(identities: Iterable[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    normalized = tuple(sorted({
        (
            canonicalize_gpu(model) or model,
            normalize_gpu_variant(canonicalize_gpu(model) or model, variant),
        )
        for model, variant in identities
    }))
    deadline = time.monotonic() + max(float(settings.KAI_CANDLE_TOTAL_TIMEOUT), 0.1)
    return _CANDLE_CACHE.get_or_load(
        ("ranking", normalized),
        max(int(settings.KAI_CANDLE_CACHE_SECONDS), 1),
        lambda: _load_ranking_metrics(normalized, deadline=deadline),
        deadline=deadline,
    )


def clear_caches() -> None:
    """Test hook; production refresh remains governed by source timestamps."""

    _PRICE_CACHE.clear()
    _CANDLE_CACHE.clear()
