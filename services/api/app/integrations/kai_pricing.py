"""Validated client for KAI's public GPU hourly-pricing API.

The integration deliberately keeps KAI's identity separate from every other
provider.  Current quotes and historical candles are accepted only when their
published schema, unit, currency and freshness are explicit; no missing value
is generated or borrowed from a legacy Vast snapshot.
"""

from __future__ import annotations

import atexit
import asyncio
from collections import defaultdict
from concurrent.futures import (
    CancelledError as FutureCancelledError,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    wait,
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
from math import ceil
import os
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
logger = logging.getLogger(__name__)


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


@dataclass
class _ClientGeneration:
    identifier: int
    client: httpx.AsyncClient
    slots: BoundedSemaphore
    accepting: bool = True
    pending: int = 0
    active: int = 0
    leases: dict[int, "_RequestLease"] = field(default_factory=dict)
    close_pending: bool = False
    close_timed_out: bool = False


@dataclass
class _RequestLease:
    identifier: int
    generation: _ClientGeneration
    deadline: float
    lock: Lock = field(default_factory=Lock)
    started: bool = False
    released: bool = False
    cancel_requested_at: float | None = None
    cancel_reason: str | None = None


class _AsyncHttpRunner:
    """One bounded async transport enforcing a true end-to-end deadline.

    httpx's scalar timeout is a per-phase inactivity timeout.  A response can
    therefore spend almost that amount in connect, first-byte and multiple
    reads.  This dedicated event loop wraps the whole request in one asyncio
    timeout, while the synchronous caller also waits only until the same
    absolute deadline.  Cancellation exits the response context and releases
    the connection instead of leaving an unbounded executor backlog.
    """

    def __init__(
        self,
        max_pending: int,
        *,
        name: str = "kai",
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        cleanup_grace: float = 0.25,
        watchdog_interval: float = 0.05,
        max_retired_generations: int = 1,
        restart_limit: int = 3,
        restart_window_seconds: float = 300,
        restart_retry_seconds: float = 5,
        fatal_recovery_threshold: float = 30,
        fatal_recovery_callback: Callable[[str, str], None] | None = None,
    ):
        self.name = str(name or "kai")
        self.max_pending = max(1, int(max_pending))
        self.cleanup_grace = max(float(cleanup_grace), 0.05)
        self.watchdog_interval = max(float(watchdog_interval), 0.01)
        self.max_retired_generations = max(int(max_retired_generations), 1)
        self.restart_limit = max(int(restart_limit), 1)
        self.restart_window_seconds = max(float(restart_window_seconds), 1)
        self.restart_retry_seconds = max(float(restart_retry_seconds), 0.1)
        self.fatal_recovery_threshold = max(float(fatal_recovery_threshold), 0.05)
        self._fatal_recovery_callback = fatal_recovery_callback
        self._client_factory = client_factory or self._default_client_factory
        self._state_lock = Lock()
        self._restart_lock = Lock()
        self._current: _ClientGeneration | None = None
        self._retired: dict[int, _ClientGeneration] = {}
        self._unused_clients: set[httpx.AsyncClient] = set()
        self._next_generation = 1
        self._next_lease = 1
        self._peak_pending = 0
        self._peak_active = 0
        self._restart_count = 0
        self._restart_suppressed_count = 0
        self._restart_failure_count = 0
        self._fatal_recovery_count = 0
        self._restart_times: list[float] = []
        self._next_restart_attempt_at = 0.0
        self._restart_pending_generation: int | None = None
        self._restart_pending_since: float | None = None
        self._unrecoverable_since: float | None = None
        self._fatal_recovery_triggered = False
        self._last_restart_reason: str | None = None
        self._last_restart_at: str | None = None
        self._close_timeout_count = 0
        self._loop_heartbeat_at = time.monotonic()
        self._closed = False
        self._ready = Event()
        self._watchdog_stop = Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._startup_error: BaseException | None = None
        self._thread = Thread(target=self._run, name="kai-http-loop", daemon=True)
        self._thread.start()
        # Loading the platform CA bundle can be noticeably slow on a cold
        # Windows process.  This happens once at module start and must not be
        # confused with an upstream request deadline.
        if not self._ready.wait(timeout=15) or self._startup_error:
            raise RuntimeError("failed to initialize KAI HTTP transport") from self._startup_error
        self._watchdog_thread = Thread(
            target=self._watchdog,
            name=f"{self.name}-http-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def _default_client_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "KAI-Star-Pricing/1.0"},
            limits=httpx.Limits(
                max_connections=self.max_pending,
                max_keepalive_connections=self.max_pending,
                # The publication cadence is five minutes.  Retaining idle
                # sockets for that entire interval caused half-closed peers to
                # be reused at the next boundary, so expire them well before it.
                keepalive_expiry=max(float(settings.KAI_PRICING_HTTP_KEEPALIVE_SECONDS), 1),
            ),
        )

    def _all_generations_locked(self) -> list[_ClientGeneration]:
        generations = list(self._retired.values())
        if self._current is not None:
            generations.append(self._current)
        return generations

    def _prune_retired_locked(self) -> None:
        removable = [
            identifier for identifier, generation in self._retired.items()
            if generation.pending == 0 and generation.active == 0 and not generation.close_pending
        ]
        for identifier in removable:
            self._retired.pop(identifier, None)

    @property
    def pending_count(self) -> int:
        with self._state_lock:
            return sum(item.pending for item in self._all_generations_locked())

    @property
    def peak_pending(self) -> int:
        with self._state_lock:
            return self._peak_pending

    @property
    def active_count(self) -> int:
        """Number of request coroutines that have actually entered the loop."""

        with self._state_lock:
            return sum(item.active for item in self._all_generations_locked())

    @property
    def peak_active(self) -> int:
        with self._state_lock:
            return self._peak_active

    def snapshot(self) -> dict[str, Any]:
        """Return a non-sensitive transport health snapshot for monitoring."""

        now = time.monotonic()
        with self._state_lock:
            self._prune_retired_locked()
            current = self._current
            pending = current.pending if current else 0
            active = current.active if current else 0
            retired_pending = sum(item.pending for item in self._retired.values())
            retired_active = sum(item.active for item in self._retired.values())
            retired_count = len(self._retired)
            leases = [
                lease
                for generation in self._all_generations_locked()
                for lease in list(generation.leases.values())
            ]
            values = {
                "generation": current.identifier if current else 0,
                "peak_pending": self._peak_pending,
                "peak_active": self._peak_active,
                "restart_count": self._restart_count,
                "restart_suppressed_count": self._restart_suppressed_count,
                "restart_failure_count": self._restart_failure_count,
                "fatal_recovery_count": self._fatal_recovery_count,
                "close_timeout_count": self._close_timeout_count,
                "last_restart_reason": self._last_restart_reason,
                "last_restart_at": self._last_restart_at,
                "heartbeat_age_ms": max(int((now - self._loop_heartbeat_at) * 1000), 0),
                "rebuild_backoff_remaining_ms": max(
                    int((self._next_restart_attempt_at - now) * 1000),
                    0,
                ),
                "unrecoverable_age_ms": (
                    max(int((now - self._unrecoverable_since) * 1000), 0)
                    if self._unrecoverable_since is not None
                    else 0
                ),
                "unrecoverable": self._unrecoverable_since is not None,
                "closed": self._closed,
            }
        stuck_requests = 0
        for lease in leases:
            with lease.lock:
                if (
                    lease.cancel_requested_at is not None
                    and not lease.released
                    and now - lease.cancel_requested_at >= self.cleanup_grace
                ):
                    stuck_requests += 1
        if values.pop("closed") or self._loop is None or not self._loop.is_running():
            state = "loop_down"
        elif values.pop("unrecoverable"):
            state = "unrecoverable"
        elif retired_count or stuck_requests:
            state = "recovering"
        elif pending >= self.max_pending:
            state = "saturated"
        elif pending:
            state = "busy"
        else:
            state = "idle"
        return {
            "name": self.name,
            "state": state,
            "generation": values["generation"],
            "capacity": self.max_pending,
            "pending": pending,
            "active": active,
            "peak_pending": values["peak_pending"],
            "peak_active": values["peak_active"],
            "retired_generation_count": retired_count,
            "retired_pending": retired_pending,
            "retired_active": retired_active,
            "stuck_requests": stuck_requests,
            "restart_count": values["restart_count"],
            "restart_suppressed_count": values["restart_suppressed_count"],
            "restart_failure_count": values["restart_failure_count"],
            "rebuild_backoff_remaining_ms": values["rebuild_backoff_remaining_ms"],
            "fatal_recovery_count": values["fatal_recovery_count"],
            "unrecoverable_age_ms": values["unrecoverable_age_ms"],
            "close_timeout_count": values["close_timeout_count"],
            "last_restart_reason": values["last_restart_reason"],
            "last_restart_at": values["last_restart_at"],
            "heartbeat_age_ms": values["heartbeat_age_ms"],
        }

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            client = self._client_factory()
            generation = _ClientGeneration(
                identifier=self._next_generation,
                client=client,
                slots=BoundedSemaphore(self.max_pending),
            )
            self._next_generation += 1
            with self._state_lock:
                self._current = generation
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
                loop.run_until_complete(self._bounded_task_drain(pending))
            with self._state_lock:
                clients = [
                    *(item.client for item in self._all_generations_locked()),
                    *self._unused_clients,
                ]
            if clients:
                loop.run_until_complete(self._bounded_client_close(clients))
            loop.close()

    async def _bounded_task_drain(self, tasks: Iterable[asyncio.Task]) -> None:
        await asyncio.wait(set(tasks), timeout=self.cleanup_grace)

    async def _bounded_client_close(self, clients: Iterable[httpx.AsyncClient]) -> None:
        tasks = {asyncio.create_task(client.aclose()) for client in clients}
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=self.cleanup_grace)
        for task in pending:
            task.cancel()

    def _heartbeat(self) -> None:
        with self._state_lock:
            self._loop_heartbeat_at = time.monotonic()

    def _watchdog(self) -> None:
        while not self._watchdog_stop.wait(self.watchdog_interval):
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._heartbeat)
            now = time.monotonic()
            with self._state_lock:
                generation = self._current
                leases = list(generation.leases.values()) if generation else []
            reason = None
            for lease in leases:
                with lease.lock:
                    if (
                        lease.cancel_requested_at is not None
                        and not lease.released
                        and now - lease.cancel_requested_at >= self.cleanup_grace
                    ):
                        reason = lease.cancel_reason or "request_deadline_exceeded"
                        break
            if generation is not None and reason:
                self._restart_transport(generation, reason)
                self._maybe_trigger_fatal_recovery(generation, reason)
            elif generation is not None:
                with self._state_lock:
                    if self._restart_pending_generation is None:
                        self._unrecoverable_since = None
                        self._fatal_recovery_triggered = False

    async def _request(
        self,
        client: httpx.AsyncClient,
        url: str,
        max_bytes: int,
        total_timeout: float,
    ) -> tuple[dict[str, Any], int]:
        content = bytearray()
        try:
            async with asyncio.timeout(total_timeout):
                timeout = httpx.Timeout(max(total_timeout, 0.1))
                async with client.stream("GET", url, timeout=timeout) as response:
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

    def _lease_started(self, lease: _RequestLease) -> bool:
        with lease.lock:
            if lease.released:
                return False
            lease.started = True
            with self._state_lock:
                lease.generation.active += 1
                total_active = sum(item.active for item in self._all_generations_locked())
                self._peak_active = max(self._peak_active, total_active)
            return True

    def _release_lease(self, lease: _RequestLease) -> bool:
        release_slot = False
        with lease.lock:
            if lease.released:
                return False
            lease.released = True
            with self._state_lock:
                generation = lease.generation
                generation.leases.pop(lease.identifier, None)
                generation.pending = max(generation.pending - 1, 0)
                if lease.started:
                    generation.active = max(generation.active - 1, 0)
                self._prune_retired_locked()
                release_slot = True
        if release_slot:
            lease.generation.slots.release()
        return release_slot

    def _mark_cancel_requested(self, lease: _RequestLease, reason: str) -> None:
        with lease.lock:
            if lease.released or lease.cancel_requested_at is not None:
                return
            lease.cancel_requested_at = time.monotonic()
            lease.cancel_reason = reason

    async def _request_and_release(
        self,
        lease: _RequestLease,
        url: str,
        max_bytes: int,
        total_timeout: float,
    ) -> tuple[dict[str, Any], int]:
        if not self._lease_started(lease):
            raise asyncio.CancelledError
        try:
            return await self._request(lease.generation.client, url, max_bytes, total_timeout)
        finally:
            self._release_lease(lease)

    def _close_generation_in_loop(self, generation: _ClientGeneration) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        with self._state_lock:
            generation.close_pending = True
        task = loop.create_task(generation.client.aclose())

        def completed(close_task: asyncio.Task) -> None:
            try:
                close_task.exception()
            except (asyncio.CancelledError, Exception):
                pass
            with self._state_lock:
                generation.close_pending = False
                self._prune_retired_locked()

        def timed_out() -> None:
            if task.done():
                return
            task.cancel()
            with self._state_lock:
                generation.close_timed_out = True
                self._close_timeout_count += 1
            logger.warning(
                "kai_http_retired_client_close_timeout pool=%s generation=%s",
                self.name,
                generation.identifier,
            )

        task.add_done_callback(completed)
        loop.call_later(self.cleanup_grace, timed_out)

    def _maybe_trigger_fatal_recovery(
        self,
        expected: _ClientGeneration,
        reason: str,
    ) -> None:
        """Escalate only after bounded client-level recovery is exhausted.

        The production API is supervised by systemd with ``Restart=always``.
        Exiting after two independently stuck generations is safer than leaking
        an unbounded number of event loops or connection pools.  Tests inject a
        harmless callback; the global runners use the supervised fail-fast
        callback only when explicitly enabled in settings.
        """

        now = time.monotonic()
        with self._state_lock:
            if self._closed or self._current is not expected:
                return
            leases = list(expected.leases.values())
        for lease in leases:
            # All request bookkeeping uses lease -> state lock order.  Keep the
            # stuck lease locked through the non-reentrant supervisor callback
            # so a concurrent finally/close cannot invalidate the final CAS.
            with lease.lock:
                if (
                    lease.released
                    or lease.cancel_requested_at is None
                    or now - lease.cancel_requested_at < self.cleanup_grace
                ):
                    continue
                with self._state_lock:
                    since = self._unrecoverable_since
                    callback = self._fatal_recovery_callback
                    if (
                        self._closed
                        or self._current is not expected
                        or expected.leases.get(lease.identifier) is not lease
                        or since is None
                        or now - since < self.fatal_recovery_threshold
                        or self._fatal_recovery_triggered
                        or callback is None
                    ):
                        return
                    self._fatal_recovery_triggered = True
                    self._fatal_recovery_count += 1
                    logger.critical(
                        "kai_http_transport_fail_fast pool=%s reason=%s",
                        self.name,
                        reason,
                    )
                    try:
                        callback(self.name, reason)
                    except Exception:
                        # A failed supervisor hook must not turn the watchdog
                        # itself into a second failure domain.  Keep serving
                        # fail-closed and expose the counter for operations.
                        logger.error(
                            "kai_http_transport_fail_fast_callback_failed pool=%s",
                            self.name,
                        )
                return

    def _close_unused_client_in_loop(self, client: httpx.AsyncClient) -> None:
        """Track an uninstalled client until its bounded shutdown completes."""

        loop = self._loop
        with self._state_lock:
            self._unused_clients.add(client)
        if loop is None or not loop.is_running():
            return
        try:
            task = loop.create_task(client.aclose())
        except RuntimeError:
            return

        def completed(close_task: asyncio.Task) -> None:
            try:
                close_task.exception()
            except (asyncio.CancelledError, Exception):
                pass
            with self._state_lock:
                self._unused_clients.discard(client)

        task.add_done_callback(completed)

    def _restart_transport(self, expected: _ClientGeneration, reason: str) -> bool:
        """Schedule a fresh client atomically; never delay a request deadline."""

        if self._closed:
            return False
        with self._restart_lock:
            now = time.monotonic()
            suppressed = False
            with self._state_lock:
                self._prune_retired_locked()
                if self._current is not expected:
                    return True
                if self._restart_pending_generation == expected.identifier:
                    if self._unrecoverable_since is None:
                        self._unrecoverable_since = self._restart_pending_since or now
                    return False
                if now < self._next_restart_attempt_at:
                    return False
                self._restart_times = [
                    value for value in self._restart_times
                    if now - value <= self.restart_window_seconds
                ]
                if (
                    len(self._retired) >= self.max_retired_generations
                    or len(self._restart_times) >= self.restart_limit
                ):
                    self._restart_suppressed_count += 1
                    self._next_restart_attempt_at = now + self.restart_retry_seconds
                    if self._unrecoverable_since is None:
                        self._unrecoverable_since = now
                    suppressed = True
                else:
                    self._restart_pending_generation = expected.identifier
                    self._restart_pending_since = now
            if suppressed:
                logger.error(
                    "kai_http_transport_restart_suppressed pool=%s generation=%s reason=%s",
                    self.name,
                    expected.identifier,
                    reason,
                )
                return False
            loop = self._loop
            if loop is None or not loop.is_running():
                with self._state_lock:
                    if self._restart_pending_generation == expected.identifier:
                        self._restart_pending_generation = None
                        self._restart_pending_since = None
                        self._restart_failure_count += 1
                        self._next_restart_attempt_at = now + self.restart_retry_seconds
                        if self._unrecoverable_since is None:
                            self._unrecoverable_since = now
                return False
            outcome = {"ok": False}

            def install() -> None:
                fresh_client: httpx.AsyncClient | None = None
                try:
                    # Avoid constructing a new TLS/client pool after shutdown or
                    # after another recovery has already replaced this one.
                    with self._state_lock:
                        if self._closed or self._current is not expected:
                            return
                    fresh_client = self._client_factory()
                    with self._state_lock:
                        if self._closed or self._current is not expected:
                            return
                        fresh = _ClientGeneration(
                            identifier=self._next_generation,
                            client=fresh_client,
                            slots=BoundedSemaphore(self.max_pending),
                        )
                        self._next_generation += 1
                        expected.accepting = False
                        self._retired[expected.identifier] = expected
                        self._current = fresh
                        self._restart_count += 1
                        self._restart_times.append(time.monotonic())
                        self._last_restart_reason = reason
                        self._last_restart_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                        self._unrecoverable_since = None
                        self._fatal_recovery_triggered = False
                        outcome["ok"] = True
                    self._close_generation_in_loop(expected)
                    logger.warning(
                        "kai_http_transport_rebuilt pool=%s old_generation=%s new_generation=%s reason=%s",
                        self.name,
                        expected.identifier,
                        fresh.identifier,
                        reason,
                    )
                except Exception:
                    with self._state_lock:
                        self._restart_failure_count += 1
                        self._next_restart_attempt_at = max(
                            self._next_restart_attempt_at,
                            time.monotonic() + self.restart_retry_seconds,
                        )
                        if self._unrecoverable_since is None:
                            self._unrecoverable_since = time.monotonic()
                    logger.error(
                        "kai_http_transport_rebuild_failed pool=%s generation=%s reason=client_creation_failed",
                        self.name,
                        expected.identifier,
                    )
                finally:
                    with self._state_lock:
                        if self._restart_pending_generation == expected.identifier:
                            self._restart_pending_generation = None
                            self._restart_pending_since = None
                    if fresh_client is not None and not outcome["ok"]:
                        self._close_unused_client_in_loop(fresh_client)

            try:
                loop.call_soon_threadsafe(install)
            except RuntimeError:
                with self._state_lock:
                    if self._restart_pending_generation == expected.identifier:
                        self._restart_pending_generation = None
                        self._restart_pending_since = None
                        self._restart_failure_count += 1
                        self._next_restart_attempt_at = time.monotonic() + self.restart_retry_seconds
                        if self._unrecoverable_since is None:
                            self._unrecoverable_since = time.monotonic()
                return False
            return True

    def _admit(self, deadline: float) -> _RequestLease:
        while True:
            remaining = deadline - time.monotonic()
            with self._state_lock:
                generation = self._current
                closed = self._closed
            if closed:
                raise KaiPricingError("upstream_error")
            if generation is None or remaining < 0.01:
                raise KaiPricingError("upstream_timeout")
            acquired = generation.slots.acquire(timeout=min(max(remaining, 0), 0.05))
            if not acquired:
                with self._state_lock:
                    changed = self._current is not generation
                if changed:
                    continue
                if time.monotonic() >= deadline:
                    raise KaiPricingError("upstream_timeout")
                continue
            with self._state_lock:
                closed = self._closed
                if closed or self._current is not generation or not generation.accepting:
                    stale = True
                else:
                    stale = False
                    lease = _RequestLease(
                        identifier=self._next_lease,
                        generation=generation,
                        deadline=deadline,
                    )
                    self._next_lease += 1
                    generation.leases[lease.identifier] = lease
                    generation.pending += 1
                    total_pending = sum(item.pending for item in self._all_generations_locked())
                    self._peak_pending = max(self._peak_pending, total_pending)
            if stale:
                generation.slots.release()
                if closed:
                    raise KaiPricingError("upstream_error")
                continue
            return lease

    def request(self, url: str, max_bytes: int, deadline: float) -> tuple[dict[str, Any], int]:
        lease = self._admit(deadline)
        loop = self._loop
        if loop is None or not loop.is_running():
            self._release_lease(lease)
            raise KaiPricingError("upstream_error")
        remaining = deadline - time.monotonic()
        if remaining < 0.05:
            self._release_lease(lease)
            raise KaiPricingError("upstream_timeout")
        cleanup_budget = min(self.cleanup_grace, max(remaining * 0.25, 0.01))
        io_timeout = max(remaining - cleanup_budget, 0.01)
        with self._state_lock:
            closed = self._closed
            if closed or self._current is not lease.generation or not lease.generation.accepting:
                stale = True
            else:
                stale = False
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._request_and_release(lease, url, max_bytes, io_timeout),
                        loop,
                    )
                except Exception:
                    future = None
        if stale or future is None:
            self._release_lease(lease)
            if closed:
                raise KaiPricingError("upstream_error")
            if stale and time.monotonic() < deadline:
                return self.request(url, max_bytes, deadline)
            raise KaiPricingError("upstream_error")

        def release_if_never_started(_future) -> None:
            with lease.lock:
                never_started = not lease.started
            if never_started:
                self._release_lease(lease)

        future.add_done_callback(release_if_never_started)
        try:
            return future.result(timeout=max(deadline - time.monotonic(), 0))
        except FutureTimeoutError as exc:
            self._mark_cancel_requested(lease, "request_deadline_exceeded")
            future.cancel()
            raise KaiPricingError("upstream_timeout") from exc
        except FutureCancelledError as exc:
            self._mark_cancel_requested(lease, "request_deadline_exceeded")
            raise KaiPricingError("upstream_timeout") from exc

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._watchdog_stop.set()
        watchdog = getattr(self, "_watchdog_thread", None)
        if watchdog is not None:
            watchdog.join(timeout=1)
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
            self._thread.join(timeout=2)


_RUNNER_OPTIONS = {
    "cleanup_grace": max(float(settings.KAI_PRICING_HTTP_CLEANUP_GRACE), 0.05),
    "max_retired_generations": max(int(settings.KAI_PRICING_HTTP_MAX_RETIRED_GENERATIONS), 1),
    "restart_limit": max(int(settings.KAI_PRICING_HTTP_RESTART_LIMIT), 1),
    "restart_window_seconds": max(int(settings.KAI_PRICING_HTTP_RESTART_WINDOW_SECONDS), 1),
    "fatal_recovery_threshold": max(float(settings.KAI_PRICING_HTTP_FAIL_FAST_SECONDS), 1),
}


def _terminate_unrecoverable_transport(pool_name: str, reason: str) -> None:
    """Let the configured service supervisor replace an unrecoverable process."""

    logger.critical(
        "kai_http_process_exit_for_transport_recovery pool=%s reason=%s exit_code=70",
        pool_name,
        reason,
    )
    os._exit(70)


# Live quotes and the much wider historical-candle fan-out must not share a
# failure domain. A wedged history connection can now degrade charts without
# starving current prices, product visibility, or purchases.
_CURRENT_RUNNER_OPTIONS = dict(_RUNNER_OPTIONS)
if settings.KAI_PRICING_HTTP_FAIL_FAST_ENABLED:
    # Only the purchase-critical live pool may ask the supervised production
    # process to restart. Historical charts remain an isolated failure domain.
    _CURRENT_RUNNER_OPTIONS["fatal_recovery_callback"] = _terminate_unrecoverable_transport
_HTTP_RUNNER = _AsyncHttpRunner(
    max_pending=max(_CANDLE_WORKERS + 2, 6),
    name="current_prices",
    **_CURRENT_RUNNER_OPTIONS,
)
_CANDLE_HTTP_RUNNER = _AsyncHttpRunner(
    max_pending=max(_CANDLE_WORKERS + 2, 6),
    name="historical_candles",
    **_RUNNER_OPTIONS,
)
atexit.register(_HTTP_RUNNER.close)
atexit.register(_CANDLE_HTTP_RUNNER.close)


def kai_http_transport_snapshot() -> dict[str, dict[str, Any]]:
    """Expose only bounded counters; never URLs, peers, headers or payloads."""

    return {
        "current_prices": _HTTP_RUNNER.snapshot(),
        "historical_candles": _CANDLE_HTTP_RUNNER.snapshot(),
    }


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
    runner: _AsyncHttpRunner | None = None,
) -> tuple[dict[str, Any], int]:
    url = f"{settings.KAI_PRICING_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    absolute_deadline = deadline or (time.monotonic() + max(float(timeout), 0.1))
    # Never start a request that cannot receive even the transport's minimum
    # scheduling budget.  The async runner enforces this deadline across all
    # network phases, not once per phase.
    if absolute_deadline - time.monotonic() < 0.1:
        raise KaiPricingError("upstream_timeout")
    return (runner or _HTTP_RUNNER).request(url, max_bytes, absolute_deadline)


def _load_price_batch(
    *,
    gpu_models: tuple[str, ...] = (),
    product_ids: tuple[str, ...] = (),
    deadline: float | None = None,
    runner: _AsyncHttpRunner | None = None,
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
        runner=runner,
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
    runner: _AsyncHttpRunner | None = None,
) -> KaiPriceBatch:
    """Return one validated KAI publication batch.

    KAI publishes atomically every five minutes.  A short cache lets the market
    and product schedulers share the same immutable batch without changing its
    source timestamp.
    """

    model_filters = tuple(sorted({str(value).strip() for value in gpu_models if str(value).strip()}))
    product_filters = tuple(sorted({str(value).strip() for value in product_ids if str(value).strip()}))
    selected_runner = runner or _HTTP_RUNNER
    loader = lambda: _load_price_batch(
        gpu_models=model_filters,
        product_ids=product_filters,
        deadline=deadline,
        runner=selected_runner,
    )
    if not use_cache:
        return loader()
    def cache_ttl(batch: KaiPriceBatch) -> float:
        until_next_publication = (batch.valid_until - utcnow()).total_seconds()
        published_interval = max(batch.refresh_interval_ms / 1000, 1)
        return max(min(until_next_publication, published_interval), 1)

    return _PRICE_CACHE.get_or_load(
        ("prices", selected_runner.name, model_filters, product_filters),
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


def _select_centered_price_candidates(
    quotes: Iterable[dict[str, Any]],
    max_products: int,
) -> list[dict[str, Any]]:
    """Return a bounded deterministic cohort without changing its median.

    The former product-id prefix cap systematically excluded whichever price
    regions happened to sort last. A centered window over current prices keeps
    the full pool's middle observation(s). Matching the selected-count parity
    to the full pool makes the selected median exactly equal to the full median
    whenever the configured capacity permits it.
    """

    ordered = sorted(
        quotes,
        key=lambda item: (
            Decimal(item["price_cny"]),
            str(item.get("external_product_id") or ""),
        ),
    )
    if not ordered:
        return []
    selected_count = min(len(ordered), max(int(max_products), 1))
    if (
        selected_count < len(ordered)
        and selected_count > 1
        and selected_count % 2 != len(ordered) % 2
    ):
        selected_count -= 1
    start = (len(ordered) - selected_count) // 2
    return ordered[start:start + selected_count]


_RANGE_CONFIG = {
    "1h": (timedelta(hours=1), "1h", 3600, 1),
    "6h": (timedelta(hours=6), "1h", 3600, 1),
    "24h": (timedelta(hours=24), "1h", 3600, 1),
    # Chart history uses the finest native KAI interval that remains bounded
    # for the requested window. Ranking keeps its separate four-hour contract
    # below so increasing chart density cannot expand the bulk ranking fanout.
    "7d": (timedelta(days=7), "1h", 3600, 1),
    "30d": (timedelta(days=30), "4h", 4 * 3600, 1),
    "90d": (timedelta(days=90), "1d", 24 * 3600, 3),
}

_RANKING_RANGE_CONFIG = (timedelta(days=7), "4h", 4 * 3600, 1)


def _expected_candle_count(duration: timedelta, interval_seconds: int) -> int:
    return max(ceil(duration.total_seconds() / interval_seconds), 1)


def _history_freshness(
    *,
    history_as_of: datetime,
    reference_at: datetime,
    duration: timedelta,
    interval_seconds: int,
) -> tuple[int, int, str]:
    """Classify provider history without silently blessing an old window."""

    if history_as_of > reference_at:
        raise KaiPricingError("upstream_invalid_response")
    lag_seconds = int((reference_at - history_as_of).total_seconds())
    stale_after_seconds = int(max(
        interval_seconds * 2,
        min(duration.total_seconds() / 2, 24 * 60 * 60),
    ))
    return (
        lag_seconds,
        stale_after_seconds,
        "stale" if lag_seconds > stale_after_seconds else "current",
    )


# KAI's ``gpuModel`` filter is exact.  These are observed public display names
# whose vendor/generation token is intentionally removed by ZTW's canonical
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

    KAI's filter is exact.  ZTW intentionally keeps only a small documented
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
        runner=_CANDLE_HTTP_RUNNER,
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
    now = utcnow()
    if (
        data_months != expected_months
        or meta_months != expected_months
        or meta_interval_ms != interval_seconds * 1000
        or data_version < 1
        or meta_from >= meta_to
        or meta_to > meta_as_of
        or meta_as_of > now
        or meta_to > now
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
        if observed < meta_from or observed > meta_to or observed > now:
            return None
        # ``asOf`` is the bucket start. KAI may include the currently open
        # bucket at ``meta.to``; it is valid metadata but not historical OHLC
        # yet. Ignore it before inspecting OHLC fields because an open bucket
        # cannot validate or invalidate the closed historical series.
        candle_end = observed + timedelta(seconds=interval_seconds)
        closed_through = min(meta_as_of, meta_to, until, now)
        if candle_end > closed_through:
            continue
        values = {name: _positive_decimal(raw.get(name)) for name in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            return None
        body_low = min(values["open"], values["close"])
        body_high = max(values["open"], values["close"])
        # KAI serializes prices to six decimal places. A few otherwise valid
        # products expose a high/low one final decimal unit inside the candle
        # body (for example high=24.790000, close=24.790001). Normalise only
        # that transport-rounding ULP; a larger structural OHLC violation still
        # rejects the series.
        rounding_ulp = Decimal("0.000001")
        if values["low"] > body_low:
            if values["low"] - body_low > rounding_ulp:
                return None
            values["low"] = body_low
        if values["high"] < body_high:
            if body_high - values["high"] > rounding_ulp:
                return None
            values["high"] = body_high
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
    # A candle represents the full half-open [start, end) interval. Coverage
    # therefore includes the final candle's end instead of measuring only the
    # distance between candle starts (which made every exact window one bucket
    # short and incorrectly labelled it partial).
    coverage = (
        parsed[-1]["observed_at"]
        + timedelta(seconds=interval_seconds)
        - parsed[0]["observed_at"]
    ).total_seconds()
    required = max((until - since).total_seconds(), 0)
    coverage_class = (
        "single" if len(parsed) == 1
        else "full" if coverage >= required
        else "partial"
    )
    return KaiCandleSeries(tuple(parsed), coverage_class, coverage)


def _window_candle_series(
    candles: Iterable[dict[str, Any]],
    *,
    anchor_start: datetime,
    duration: timedelta,
    interval_seconds: int,
) -> KaiCandleSeries:
    """Return a provider-anchored trailing window without inventing buckets."""

    interval = timedelta(seconds=interval_seconds)
    window_start = anchor_start + interval - duration
    selected = tuple(
        item for item in candles
        if window_start <= item["observed_at"] <= anchor_start
    )
    if not selected:
        return KaiCandleSeries((), "single", 0.0)
    coverage = (
        selected[-1]["observed_at"] + interval - selected[0]["observed_at"]
    ).total_seconds()
    expected_count = _expected_candle_count(duration, interval_seconds)
    coverage_class = (
        "single" if len(selected) == 1
        else "full" if (
            len(selected) == expected_count
            and coverage == duration.total_seconds()
        )
        else "partial"
    )
    return KaiCandleSeries(selected, coverage_class, coverage)


def _latest_reasonable_candle_cohort(
    selected: list[tuple[dict[str, Any], KaiCandleSeries]],
) -> tuple[datetime, list[tuple[dict[str, Any], KaiCandleSeries]]]:
    """Choose the newest candle start shared by at least half the regions."""

    timestamp_sets = [
        {item["observed_at"] for item in series.candles}
        for _candidate, series in selected
    ]
    minimum_members = max(1, ceil(len(selected) / 2))
    for anchor_start in sorted(set().union(*timestamp_sets), reverse=True):
        cohort = [
            item for item, timestamps in zip(selected, timestamp_sets)
            if anchor_start in timestamps
        ]
        if len(cohort) >= minimum_members:
            return anchor_start, cohort
    raise KaiPricingError("history_unavailable")


def _fixed_candle_cohort_window(
    selected: list[tuple[dict[str, Any], KaiCandleSeries]],
    *,
    anchor_start: datetime,
    duration: timedelta,
    interval_seconds: int,
    minimum_members: int,
) -> tuple[
    datetime,
    list[tuple[dict[str, Any], KaiCandleSeries]],
    tuple[datetime, ...],
]:
    """Choose one fixed minimum-half cohort for the longest anchored window.

    Every parsed product series is already strictly consecutive. For a
    trailing window ending at ``anchor_start``, the longest window covered by
    at least N products therefore starts at the Nth-earliest available start.
    Including every additional product that also covers that start maximises
    membership without shortening the window. No missing timestamp is ever
    generated or filled.
    """

    interval = timedelta(seconds=interval_seconds)
    requested_window_start = anchor_start + interval - duration
    anchored: list[
        tuple[datetime, tuple[dict[str, Any], KaiCandleSeries]]
    ] = []
    for item in selected:
        _candidate, series = item
        timestamps = {candle["observed_at"] for candle in series.candles}
        if anchor_start not in timestamps:
            continue
        available_start = max(
            series.candles[0]["observed_at"],
            requested_window_start,
        )
        anchored.append((available_start, item))

    required = max(int(minimum_members), 1)
    if len(anchored) < required:
        raise KaiPricingError("history_unavailable")

    window_start = sorted(start for start, _item in anchored)[required - 1]
    cohort = [
        item for available_start, item in anchored
        if available_start <= window_start
    ]
    cohort.sort(key=lambda item: item[0]["external_product_id"])

    common_timestamps: set[datetime] | None = None
    for _candidate, series in cohort:
        member_timestamps = {
            candle["observed_at"] for candle in series.candles
            if window_start <= candle["observed_at"] <= anchor_start
        }
        common_timestamps = (
            member_timestamps
            if common_timestamps is None
            else common_timestamps & member_timestamps
        )
    timestamps = tuple(sorted(common_timestamps or ()))
    expected_count = int(
        (anchor_start - window_start).total_seconds() / interval_seconds
    ) + 1
    if (
        len(timestamps) != expected_count
        or not timestamps
        or timestamps[0] != window_start
        or timestamps[-1] != anchor_start
        or any(
            current - previous != interval
            for previous, current in zip(timestamps, timestamps[1:])
        )
    ):
        raise KaiPricingError("history_unavailable")
    return window_start, cohort, timestamps


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
    batch = fetch_price_batch(
        gpu_models=filters,
        deadline=deadline,
        runner=_CANDLE_HTTP_RUNNER,
    )
    if time.monotonic() >= deadline:
        raise KaiPricingError("upstream_timeout")
    quotes = [
        item for item in normalized_current_quotes(batch)
        if item["gpu_model"] == model and item["gpu_variant"] == variant
    ]
    candidates = _select_centered_price_candidates(
        quotes,
        settings.KAI_CANDLE_MAX_PRODUCTS,
    )
    if not candidates:
        raise KaiPricingError("history_unavailable")
    full_pool_live_price = _median([
        Decimal(item["price_cny"])
        for item in quotes
    ])

    live_observed_at = batch.observed_at
    requested_since = live_observed_at - duration
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
                since=requested_since,
                until=live_observed_at,
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

    validated_product_count = len(selected)
    minimum_cohort_members = max(1, ceil(validated_product_count / 2))
    # One very stale region must not pull every current region backwards. The
    # newest candle shared by a majority is deterministic, remains genuinely
    # cross-region, and still permits one valid region when only one exists.
    anchor_start, selected = _latest_reasonable_candle_cohort(selected)
    anchor_cohort_product_count = len(selected)
    window_start, selected, selected_timestamps = _fixed_candle_cohort_window(
        selected,
        anchor_start=anchor_start,
        duration=duration,
        interval_seconds=interval_seconds,
        minimum_members=minimum_cohort_members,
    )
    candle_indexes = [
        {candle["observed_at"]: candle for candle in series.candles}
        for _candidate, series in selected
    ]
    candles: list[dict[str, Any]] = []
    for observed_at in selected_timestamps:
        rows = [index[observed_at] for index in candle_indexes]
        aggregated: dict[str, Decimal] = {}
        for name in ("open", "high", "low", "close"):
            aggregated[name] = _median([Decimal(row[name]) for row in rows])
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
    successful_cohort_live_price = _median(latest_prices)
    live_price_deviation_ratio = (
        abs(successful_cohort_live_price - full_pool_live_price) / full_pool_live_price
        if full_pool_live_price > 0 else Decimal("0")
    )
    latest_live_comparable = successful_cohort_live_price == full_pool_live_price
    first_time = _parse_datetime(candles[0]["start_time"])
    last_end_time = _parse_datetime(candles[-1]["end_time"])
    coverage_span_seconds = (last_end_time - first_time).total_seconds()
    expected_count = _expected_candle_count(duration, interval_seconds)
    raw_coverage_class = (
        "single" if len(candles) == 1
        else "full" if (
            len(candles) == expected_count
            and coverage_span_seconds == duration.total_seconds()
        )
        else "partial"
    )
    history_lag_seconds, stale_after_seconds, freshness_status = _history_freshness(
        history_as_of=last_end_time,
        reference_at=batch.observed_at,
        duration=duration,
        interval_seconds=interval_seconds,
    )
    coverage_class = (
        "partial" if raw_coverage_class == "full" and freshness_status == "stale"
        else raw_coverage_class
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
            "history_as_of": last_end_time.isoformat(timespec="seconds") + "Z",
            "history_lag_seconds": history_lag_seconds,
            "history_freshness_status": freshness_status,
            "history_stale_after_seconds": stale_after_seconds,
            "raw_coverage_class": raw_coverage_class,
            "product_selection": "fixed_minimum_half_continuous_window_cohort",
            "candidate_sampling_method": "current_price_centered_parity_matched",
            "current_quote_filter": "exact_gpuModel_query",
            "candidate_product_count": len(quotes),
            "sampled_candidate_product_count": len(candidates),
            "sampled_candidate_product_ids": [
                item["external_product_id"] for item in candidates
            ],
            "validated_product_count": validated_product_count,
            "anchor_cohort_product_count": anchor_cohort_product_count,
            "selected_product_count": len(selected_ids),
            "cohort_min_product_count": minimum_cohort_members,
            "selected_product_ids": selected_ids,
            "fixed_cohort_product_count": len(selected_ids),
            "fixed_cohort_product_ids": selected_ids,
            "fixed_cohort_window_start": window_start.isoformat(timespec="seconds") + "Z",
            "fixed_cohort_anchor_start": anchor_start.isoformat(timespec="seconds") + "Z",
            "selection_completeness": (
                "full"
                if len(selected_ids) == len(candidates)
                else "latest_reasonable_cohort"
                if validated_product_count == len(candidates)
                else "partial_before_deadline"
            ),
            "max_products": int(settings.KAI_CANDLE_MAX_PRODUCTS),
            "aggregation": "fixed_cohort_median_for_each_ohlc_field",
            "latest_live_full_pool_median_price_cny": float(full_pool_live_price),
            "latest_live_successful_cohort_median_price_cny": float(successful_cohort_live_price),
            "latest_live_median_deviation_ratio": float(live_price_deviation_ratio),
            "interval": interval,
            "cache_seconds": int(settings.KAI_CANDLE_CACHE_SECONDS),
            "live_component_included": False,
            "coverage_quality": coverage["coverage_quality"],
        },
        "latest_live_price_cny": float(full_pool_live_price),
        "latest_live_observed_at": batch.observed_at.isoformat(timespec="seconds") + "Z",
        "latest_live_comparable_to_history": latest_live_comparable,
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
    batch = fetch_price_batch(
        product_ids=(product_id,),
        deadline=deadline,
        runner=_CANDLE_HTTP_RUNNER,
    )
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
    requested_since = batch.observed_at - duration
    parsed_series = _parse_complete_candle_series(
        payload,
        product_id=product_id,
        since=requested_since,
        until=batch.observed_at,
        interval_seconds=interval_seconds,
        expected_interval=interval,
        expected_months=months,
    )
    if not parsed_series:
        raise KaiPricingError("history_unavailable")
    series = _window_candle_series(
        parsed_series.candles,
        anchor_start=parsed_series.candles[-1]["observed_at"],
        duration=duration,
        interval_seconds=interval_seconds,
    )
    if not series.candles:
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
    last_time = series.candles[-1]["observed_at"]
    history_as_of = last_time + timedelta(seconds=interval_seconds)
    history_lag_seconds, stale_after_seconds, freshness_status = _history_freshness(
        history_as_of=history_as_of,
        reference_at=batch.observed_at,
        duration=duration,
        interval_seconds=interval_seconds,
    )
    coverage_class = (
        "partial" if series.coverage_class == "full" and freshness_status == "stale"
        else series.coverage_class
    )
    coverage = _coverage_contract(coverage_class)
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
        "coverage_class": coverage_class,
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
            "history_as_of": history_as_of.isoformat(timespec="seconds") + "Z",
            "history_lag_seconds": history_lag_seconds,
            "history_freshness_status": freshness_status,
            "history_stale_after_seconds": stale_after_seconds,
            "raw_coverage_class": series.coverage_class,
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
    batch = fetch_price_batch(
        gpu_models=model_filters,
        deadline=deadline,
        runner=_CANDLE_HTTP_RUNNER,
    )
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

    duration, interval, interval_seconds, months = _RANKING_RANGE_CONFIG
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
            parsed_series = _parse_complete_candle_series(
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
        if not parsed_series:
            continue
        series = _window_candle_series(
            parsed_series.candles,
            anchor_start=parsed_series.candles[-1]["observed_at"],
            duration=duration,
            interval_seconds=interval_seconds,
        )
        if not series.candles:
            continue
        candles = series.candles
        history_as_of = candles[-1]["observed_at"] + timedelta(seconds=interval_seconds)
        history_lag_seconds, stale_after_seconds, freshness_status = _history_freshness(
            history_as_of=history_as_of,
            reference_at=batch.observed_at,
            duration=duration,
            interval_seconds=interval_seconds,
        )
        lows = [Decimal(item["low"]) for item in candles]
        highs = [Decimal(item["high"]) for item in candles]
        closes = [Decimal(item["close"]) for item in candles]
        identity = (candidate["gpu_model"], candidate["gpu_variant"])
        # Short official series remain useful coverage evidence, but are never
        # promoted into a seven-day change/range/volatility claim.
        if series.coverage_class != "full" or freshness_status == "stale":
            effective_coverage = (
                "partial" if series.coverage_class == "full" else series.coverage_class
            )
            result[identity] = {
                "volatility_7d": None,
                "volatility_status": "insufficient_history",
                "volatility_quality": "limited_sample",
                "history_day_count": len({item["observed_at"].date() for item in candles}),
                "history_point_count": len(candles),
                "history_span_hours": round(series.coverage_span_seconds / 3600, 1),
                "history_min_daily_sample_count": 1,
                "history_bucket_count": len(candles),
                "history_coverage_status": effective_coverage,
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
                    "history_as_of": history_as_of.isoformat(timespec="seconds") + "Z",
                    "history_lag_seconds": history_lag_seconds,
                    "history_freshness_status": freshness_status,
                    "history_stale_after_seconds": stale_after_seconds,
                    "selected_product_id": candidate["external_product_id"],
                    "interval": interval,
                    "live_component_included": False,
                    "coverage_quality": effective_coverage,
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
            "history_span_hours": round(series.coverage_span_seconds / 3600, 1),
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
                "history_as_of": history_as_of.isoformat(timespec="seconds") + "Z",
                "history_lag_seconds": history_lag_seconds,
                "history_freshness_status": freshness_status,
                "history_stale_after_seconds": stale_after_seconds,
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
