import asyncio
import json
from threading import Event, Lock, Thread
import time
import unittest
from unittest.mock import patch

import httpx

from app.integrations.kai_pricing import (
    _AsyncHttpRunner,
    _CANDLE_HTTP_RUNNER,
    _HTTP_RUNNER,
    _aggregate_kai_candles,
    _fetch_product_candles,
    _get_json,
    _load_exact_product_candles,
    _load_ranking_metrics,
    kai_http_transport_snapshot,
    KaiPricingError,
)


class _BlockingStream(httpx.AsyncByteStream):
    """A controllable response body used to inspect live runner counters."""

    def __init__(self, started: Event, release: Event):
        self.started = started
        self.release = release

    async def __aiter__(self):
        self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(0.005)
        yield b'{"ok": true}'

    async def aclose(self):
        return None


class _CancellationResistantCloseStream(httpx.AsyncByteStream):
    """Model a response context that never acknowledges cancellation.

    The production incident left HTTP connections in CLOSE-WAIT after the
    synchronous deadline elapsed.  In that failure mode the old response
    context can remain alive indefinitely, so recovery must not depend on its
    ``aclose`` finishing.
    """

    def __init__(self, close_started: Event, release: Event, released: Event):
        self.close_started = close_started
        self.release = release
        self.released = released

    async def __aiter__(self):
        yield b'{"old_generation": true}'

    async def aclose(self):
        self.close_started.set()
        try:
            while not self.release.is_set():
                try:
                    await asyncio.sleep(0.005)
                except asyncio.CancelledError:
                    # Real transports can spend an unbounded amount of time
                    # unwinding native/TLS response state after cancellation.
                    continue
        finally:
            self.released.set()


class AsyncHttpRunnerResilienceTests(unittest.TestCase):
    def test_public_snapshot_has_strict_non_sensitive_field_whitelist(self):
        expected_fields = {
            "name",
            "state",
            "generation",
            "capacity",
            "pending",
            "active",
            "peak_pending",
            "peak_active",
            "retired_generation_count",
            "retired_pending",
            "retired_active",
            "stuck_requests",
            "restart_count",
            "restart_failure_count",
            "restart_suppressed_count",
            "rebuild_backoff_remaining_ms",
            "close_timeout_count",
            "fatal_recovery_count",
            "unrecoverable_age_ms",
            "last_restart_reason",
            "last_restart_at",
            "heartbeat_age_ms",
        }

        snapshot = kai_http_transport_snapshot()

        self.assertEqual(set(snapshot), {"current_prices", "historical_candles"})
        self.assertEqual(snapshot["current_prices"]["name"], "current_prices")
        self.assertEqual(snapshot["historical_candles"]["name"], "historical_candles")
        for pool in snapshot.values():
            self.assertEqual(set(pool), expected_fields)

        serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).lower()
        for forbidden in (
            "http://",
            "https://",
            "pricing.kai",
            "authorization",
            "bearer",
            "header",
            "hostname",
            "token",
            "url",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_current_prices_and_candle_traffic_use_isolated_runners(self):
        with patch.object(
            _HTTP_RUNNER,
            "request",
            return_value=({"pool": "current"}, 18),
        ) as current_request, patch.object(
            _CANDLE_HTTP_RUNNER,
            "request",
            return_value=({"pool": "candles"}, 18),
        ) as candle_request:
            current_payload, _size = _get_json(
                "/v1/prices",
                timeout=1,
                max_bytes=1024,
            )
            self.assertEqual(current_payload, {"pool": "current"})
            current_request.assert_called_once()
            candle_request.assert_not_called()

            current_request.reset_mock()
            candle_request.reset_mock()
            candle_payload, _size = _fetch_product_candles(
                "kai-product-id",
                "4h",
                deadline=time.monotonic() + 1,
            )
            self.assertEqual(candle_payload, {"pool": "candles"})
            candle_request.assert_called_once()
            current_request.assert_not_called()

        # Aggregation first asks for a narrowly filtered current quote batch.
        # That request belongs to the history failure domain as well; otherwise
        # a wedged chart fan-out could still consume the live-price pool.
        sentinel = KaiPricingError("sentinel")
        with patch(
            "app.integrations.kai_pricing.fetch_price_batch",
            side_effect=sentinel,
        ) as filtered_prices:
            with self.assertRaises(KaiPricingError) as raised:
                _aggregate_kai_candles(
                    "RTX4090",
                    "24GB",
                    "7d",
                    deadline=time.monotonic() + 1,
                )
        self.assertIs(raised.exception, sentinel)
        self.assertIs(filtered_prices.call_args.kwargs["runner"], _CANDLE_HTTP_RUNNER)

    def test_exact_product_and_ranking_filter_prices_use_candle_runner(self):
        sentinel = KaiPricingError("sentinel")
        loaders = (
            lambda: _load_exact_product_candles(
                "kai-product-id",
                "RTX4090",
                "24GB",
                "7d",
                deadline=time.monotonic() + 1,
            ),
            lambda: _load_ranking_metrics(
                (("RTX4090", "24GB"),),
                deadline=time.monotonic() + 1,
            ),
        )
        for loader in loaders:
            with self.subTest(loader=loader), patch(
                "app.integrations.kai_pricing.fetch_price_batch",
                side_effect=sentinel,
            ) as filtered_prices:
                with self.assertRaises(KaiPricingError) as raised:
                    loader()
                self.assertIs(raised.exception, sentinel)
                self.assertIs(
                    filtered_prices.call_args.kwargs["runner"],
                    _CANDLE_HTTP_RUNNER,
                )

    def test_cooperative_timeout_releases_slot_without_restarting_transport(self):
        started = Event()
        release = Event()
        request_lock = Lock()
        request_count = 0

        async def handler(_request):
            nonlocal request_count
            with request_lock:
                request_count += 1
                current = request_count
            if current == 1:
                return httpx.Response(200, stream=_BlockingStream(started, release))
            return httpx.Response(200, json={"request": current})

        def client_factory():
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(max_pending=1, client_factory=client_factory)
        try:
            original_generation = runner.snapshot()["generation"]
            with self.assertRaises(KaiPricingError) as raised:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertEqual(raised.exception.code, "upstream_timeout")
            self.assertTrue(started.wait(timeout=1))

            until = time.monotonic() + 0.5
            while runner.snapshot()["pending"] and time.monotonic() < until:
                time.sleep(0.005)
            after_timeout = runner.snapshot()
            self.assertEqual(after_timeout["generation"], original_generation)
            self.assertEqual(after_timeout["restart_count"], 0)
            self.assertEqual(after_timeout["pending"], 0)
            self.assertEqual(after_timeout["active"], 0)

            payload, _size = runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
            self.assertEqual(payload, {"request": 2})
            self.assertEqual(runner.snapshot()["generation"], original_generation)
        finally:
            release.set()
            runner.close()

    def test_snapshot_tracks_live_and_peak_request_counts(self):
        started = Event()
        release = Event()

        async def handler(_request):
            return httpx.Response(200, stream=_BlockingStream(started, release))

        def client_factory():
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(max_pending=2, client_factory=client_factory)
        result = []
        error = []

        def make_request():
            try:
                result.append(runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 2,
                ))
            except BaseException as exc:  # preserve the worker failure for the assertion
                error.append(exc)

        worker = Thread(target=make_request, daemon=True)
        try:
            initial = runner.snapshot()
            self.assertEqual(initial["generation"], 1)
            self.assertEqual(initial["pending"], 0)
            self.assertEqual(initial["active"], 0)
            self.assertEqual(initial["restart_count"], 0)

            worker.start()
            self.assertTrue(started.wait(timeout=1))
            live = runner.snapshot()
            self.assertEqual(live["pending"], 1)
            self.assertEqual(live["active"], 1)
            self.assertEqual(live["peak_pending"], 1)
            self.assertEqual(live["peak_active"], 1)

            release.set()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(error, [])
            self.assertEqual(result, [({"ok": True}, 12)])

            finished = runner.snapshot()
            self.assertEqual(finished["pending"], 0)
            self.assertEqual(finished["active"], 0)
            self.assertEqual(finished["peak_pending"], 1)
            self.assertEqual(finished["peak_active"], 1)
        finally:
            release.set()
            worker.join(timeout=1)
            runner.close()

    def test_stuck_response_context_rotates_transport_and_recovers_capacity(self):
        close_started = Event()
        release_old = Event()
        old_released = Event()
        current_started = Event()
        release_current = Event()
        factory_lock = Lock()
        factory_count = 0
        fresh_request_count = 0

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                nonlocal fresh_request_count
                if generation == 1:
                    return httpx.Response(
                        200,
                        stream=_CancellationResistantCloseStream(
                            close_started,
                            release_old,
                            old_released,
                        ),
                    )
                with factory_lock:
                    fresh_request_count += 1
                    current_request = fresh_request_count
                if current_request == 2:
                    return httpx.Response(
                        200,
                        stream=_BlockingStream(current_started, release_current),
                    )
                return httpx.Response(200, json={"generation": generation})

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(max_pending=1, client_factory=client_factory)
        try:
            with self.assertRaises(KaiPricingError) as raised:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertEqual(raised.exception.code, "upstream_timeout")
            self.assertTrue(close_started.wait(timeout=1))

            # Recovery must not wait for the cancellation-resistant response
            # context.  A fresh request is admitted by a new generation.
            payload, _size = runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
            self.assertGreaterEqual(payload["generation"], 2)
            recovered = runner.snapshot()
            self.assertGreaterEqual(recovered["generation"], 2)
            self.assertGreaterEqual(recovered["restart_count"], 1)
            self.assertEqual(recovered["last_restart_reason"], "request_deadline_exceeded")
            self.assertEqual(recovered["pending"], 0)
            self.assertEqual(recovered["active"], 0)

            # A late finally from the retired generation must update only its
            # own counters.  Keep a new-generation request active so an
            # accidental decrement/release against current state is visible.
            current_generation = recovered["generation"]
            current_restarts = recovered["restart_count"]
            current_result = []
            current_error = []

            def hold_current_generation():
                try:
                    current_result.append(runner.request(
                        "https://pricing.kai.test/v1/prices",
                        1024,
                        time.monotonic() + 2,
                    ))
                except BaseException as exc:
                    current_error.append(exc)

            current_worker = Thread(target=hold_current_generation, daemon=True)
            current_worker.start()
            self.assertTrue(current_started.wait(timeout=1))
            before_old_release = runner.snapshot()
            self.assertEqual(before_old_release["pending"], 1)
            self.assertEqual(before_old_release["active"], 1)

            release_old.set()
            self.assertTrue(old_released.wait(timeout=1))
            time.sleep(0.02)
            after_old_release = runner.snapshot()
            self.assertEqual(after_old_release["generation"], current_generation)
            self.assertEqual(after_old_release["restart_count"], current_restarts)
            self.assertEqual(after_old_release["pending"], 1)
            self.assertEqual(after_old_release["active"], 1)

            release_current.set()
            current_worker.join(timeout=1)
            self.assertFalse(current_worker.is_alive())
            self.assertEqual(current_error, [])
            self.assertEqual(current_result, [({"ok": True}, 12)])
            self.assertEqual(runner.snapshot()["pending"], 0)
            self.assertEqual(runner.snapshot()["active"], 0)

            final_payload, _size = runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
            self.assertEqual(final_payload["generation"], current_generation)
        finally:
            release_old.set()
            release_current.set()
            old_released.wait(timeout=1)
            runner.close()

    def test_healthy_slow_request_causing_admission_timeout_does_not_restart(self):
        old_started = Event()
        release_old = Event()
        factory_lock = Lock()
        factory_count = 0

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                if generation == 1:
                    return httpx.Response(200, stream=_BlockingStream(old_started, release_old))
                return httpx.Response(200, json={"generation": generation})

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(max_pending=1, client_factory=client_factory)
        first_error = []

        def occupy_only_slot():
            try:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 2,
                )
            except BaseException as exc:
                first_error.append(exc)

        occupying = Thread(target=occupy_only_slot, daemon=True)
        try:
            occupying.start()
            self.assertTrue(old_started.wait(timeout=1))

            with self.assertRaises(KaiPricingError) as raised:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.12,
                )
            self.assertEqual(raised.exception.code, "upstream_timeout")

            snapshot = runner.snapshot()
            self.assertEqual(snapshot["restart_count"], 0)
            self.assertIsNone(snapshot["last_restart_reason"])
            self.assertEqual(snapshot["generation"], 1)

            # The occupant is healthy: once it completes, the same transport
            # generation must retain and reuse its full capacity.
            release_old.set()
            occupying.join(timeout=1)
            self.assertFalse(occupying.is_alive())
            self.assertEqual(first_error, [])

            payload, _size = runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
            self.assertEqual(payload, {"ok": True})
            self.assertEqual(runner.snapshot()["generation"], snapshot["generation"])
            self.assertEqual(runner.snapshot()["pending"], 0)
            self.assertEqual(runner.snapshot()["active"], 0)
        finally:
            release_old.set()
            occupying.join(timeout=1)
            runner.close()

    def test_second_stuck_generation_is_suppressed_while_retired_pool_is_live(self):
        first_close_started = Event()
        second_close_started = Event()
        release_first = Event()
        release_second = Event()
        first_released = Event()
        second_released = Event()
        factory_lock = Lock()
        factory_count = 0

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                if generation == 1:
                    stream = _CancellationResistantCloseStream(
                        first_close_started,
                        release_first,
                        first_released,
                    )
                else:
                    stream = _CancellationResistantCloseStream(
                        second_close_started,
                        release_second,
                        second_released,
                    )
                return httpx.Response(200, stream=stream)

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            max_retired_generations=1,
        )
        try:
            with self.assertRaises(KaiPricingError) as first_timeout:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertEqual(first_timeout.exception.code, "upstream_timeout")
            self.assertTrue(first_close_started.wait(timeout=1))

            until = time.monotonic() + 1
            while runner.snapshot()["generation"] == 1 and time.monotonic() < until:
                time.sleep(0.005)
            first_recovery = runner.snapshot()
            self.assertEqual(first_recovery["generation"], 2)
            self.assertEqual(first_recovery["restart_count"], 1)
            self.assertEqual(first_recovery["retired_generation_count"], 1)

            with self.assertRaises(KaiPricingError) as second_timeout:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertEqual(second_timeout.exception.code, "upstream_timeout")
            self.assertTrue(second_close_started.wait(timeout=1))

            until = time.monotonic() + 1
            while runner.snapshot()["restart_suppressed_count"] == 0 and time.monotonic() < until:
                time.sleep(0.005)
            suppressed = runner.snapshot()
            self.assertEqual(suppressed["generation"], 2)
            self.assertEqual(suppressed["restart_count"], 1)
            self.assertEqual(suppressed["retired_generation_count"], 1)
            self.assertGreaterEqual(suppressed["restart_suppressed_count"], 1)
            self.assertLessEqual(
                suppressed["retired_active"] + suppressed["active"],
                runner.max_pending * 2,
            )
        finally:
            release_first.set()
            release_second.set()
            first_released.wait(timeout=1)
            second_released.wait(timeout=1)
            runner.close()

    def test_request_after_close_fails_fast_as_upstream_error(self):
        async def handler(_request):
            return httpx.Response(200, json={"ok": True})

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            ),
        )
        runner.close()

        started = time.monotonic()
        with self.assertRaises(KaiPricingError) as raised:
            runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
        elapsed = time.monotonic() - started

        self.assertEqual(raised.exception.code, "upstream_error")
        self.assertLess(elapsed, 0.2)

    def test_rebuild_factory_failure_is_counted_and_backed_off(self):
        close_started = Event()
        release = Event()
        released = Event()
        factory_lock = Lock()
        factory_calls = 0

        def client_factory():
            nonlocal factory_calls
            with factory_lock:
                factory_calls += 1
                call = factory_calls
            if call > 1:
                raise RuntimeError("synthetic client construction failure")

            async def handler(_request):
                return httpx.Response(
                    200,
                    stream=_CancellationResistantCloseStream(
                        close_started,
                        release,
                        released,
                    ),
                )

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            restart_retry_seconds=0.2,
            fatal_recovery_threshold=100,
        )
        try:
            with self.assertRaises(KaiPricingError) as timeout:
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertEqual(timeout.exception.code, "upstream_timeout")
            self.assertTrue(close_started.wait(timeout=1))

            until = time.monotonic() + 1
            while runner.snapshot()["restart_failure_count"] == 0 and time.monotonic() < until:
                time.sleep(0.005)
            failed = runner.snapshot()
            self.assertEqual(failed["generation"], 1)
            self.assertEqual(failed["restart_count"], 0)
            self.assertEqual(failed["restart_failure_count"], 1)
            self.assertGreater(failed["rebuild_backoff_remaining_ms"], 0)

            with factory_lock:
                calls_after_failure = factory_calls
            time.sleep(0.08)
            with factory_lock:
                self.assertEqual(factory_calls, calls_after_failure)
        finally:
            release.set()
            released.wait(timeout=1)
            runner.close()

    def test_persistent_stuck_current_pool_invokes_injected_fatal_recovery_once(self):
        first_close_started = Event()
        second_close_started = Event()
        release_first = Event()
        release_second = Event()
        first_released = Event()
        second_released = Event()
        fatal_called = Event()
        fatal_lock = Lock()
        fatal_calls = []
        factory_lock = Lock()
        factory_count = 0

        def fatal_recovery(pool_name: str, reason: str):
            with fatal_lock:
                fatal_calls.append((pool_name, reason))
            fatal_called.set()

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                if generation == 1:
                    stream = _CancellationResistantCloseStream(
                        first_close_started,
                        release_first,
                        first_released,
                    )
                else:
                    stream = _CancellationResistantCloseStream(
                        second_close_started,
                        release_second,
                        second_released,
                    )
                return httpx.Response(200, stream=stream)

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            name="fatal-test",
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            max_retired_generations=1,
            restart_retry_seconds=0.1,
            fatal_recovery_callback=fatal_recovery,
            fatal_recovery_threshold=0.1,
        )
        try:
            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(first_close_started.wait(timeout=1))
            until = time.monotonic() + 1
            while runner.snapshot()["generation"] == 1 and time.monotonic() < until:
                time.sleep(0.005)
            self.assertEqual(runner.snapshot()["retired_generation_count"], 1)

            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(second_close_started.wait(timeout=1))
            self.assertTrue(fatal_called.wait(timeout=1))

            fatal_snapshot = runner.snapshot()
            self.assertEqual(fatal_snapshot["generation"], 2)
            self.assertEqual(fatal_snapshot["restart_count"], 1)
            self.assertEqual(fatal_snapshot["retired_generation_count"], 1)
            self.assertGreaterEqual(fatal_snapshot["restart_suppressed_count"], 2)
            self.assertEqual(fatal_snapshot["fatal_recovery_count"], 1)
            self.assertGreater(fatal_snapshot["unrecoverable_age_ms"], 0)
            with fatal_lock:
                self.assertEqual(len(fatal_calls), 1)
                self.assertEqual(fatal_calls[0][0], "fatal-test")
                self.assertTrue(fatal_calls[0][1])

            # Once escalated, the watchdog must not spam the supervisor hook.
            time.sleep(0.2)
            with fatal_lock:
                self.assertEqual(len(fatal_calls), 1)
        finally:
            release_first.set()
            release_second.set()
            first_released.wait(timeout=1)
            second_released.wait(timeout=1)
            runner.close()

    def test_releasing_second_generation_before_threshold_clears_fatal_state(self):
        first_close_started = Event()
        second_close_started = Event()
        release_first = Event()
        release_second = Event()
        first_released = Event()
        second_released = Event()
        fatal_called = Event()
        factory_lock = Lock()
        factory_count = 0

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                stream = (
                    _CancellationResistantCloseStream(
                        first_close_started,
                        release_first,
                        first_released,
                    )
                    if generation == 1
                    else _CancellationResistantCloseStream(
                        second_close_started,
                        release_second,
                        second_released,
                    )
                )
                return httpx.Response(200, stream=stream)

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            max_retired_generations=1,
            restart_retry_seconds=0.1,
            fatal_recovery_callback=lambda _pool, _reason: fatal_called.set(),
            fatal_recovery_threshold=0.35,
        )
        try:
            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(first_close_started.wait(timeout=1))
            until = time.monotonic() + 1
            while runner.snapshot()["generation"] == 1 and time.monotonic() < until:
                time.sleep(0.005)

            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(second_close_started.wait(timeout=1))
            until = time.monotonic() + 1
            while runner.snapshot()["unrecoverable_age_ms"] == 0 and time.monotonic() < until:
                time.sleep(0.005)
            self.assertGreater(runner.snapshot()["unrecoverable_age_ms"], 0)

            # Current-generation progress before the threshold means process
            # recovery is no longer warranted, even though an older retired
            # response context is still unwinding.
            release_second.set()
            self.assertTrue(second_released.wait(timeout=1))
            time.sleep(0.4)
            recovered = runner.snapshot()
            self.assertFalse(fatal_called.is_set())
            self.assertEqual(recovered["fatal_recovery_count"], 0)
            self.assertEqual(recovered["unrecoverable_age_ms"], 0)
            self.assertEqual(recovered["generation"], 2)
        finally:
            release_first.set()
            release_second.set()
            first_released.wait(timeout=1)
            second_released.wait(timeout=1)
            runner.close()

    def test_close_from_unrecoverable_state_cannot_invoke_fatal_callback(self):
        first_close_started = Event()
        second_close_started = Event()
        release_first = Event()
        release_second = Event()
        first_released = Event()
        second_released = Event()
        fatal_called = Event()
        factory_lock = Lock()
        factory_count = 0

        def client_factory():
            nonlocal factory_count
            with factory_lock:
                factory_count += 1
                generation = factory_count

            async def handler(_request):
                stream = (
                    _CancellationResistantCloseStream(
                        first_close_started,
                        release_first,
                        first_released,
                    )
                    if generation == 1
                    else _CancellationResistantCloseStream(
                        second_close_started,
                        release_second,
                        second_released,
                    )
                )
                return httpx.Response(200, stream=stream)

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            max_retired_generations=1,
            restart_retry_seconds=0.1,
            fatal_recovery_callback=lambda _pool, _reason: fatal_called.set(),
            fatal_recovery_threshold=0.35,
        )
        closer = None
        try:
            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(first_close_started.wait(timeout=1))
            until = time.monotonic() + 1
            while runner.snapshot()["generation"] == 1 and time.monotonic() < until:
                time.sleep(0.005)

            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(second_close_started.wait(timeout=1))
            until = time.monotonic() + 1
            while runner.snapshot()["unrecoverable_age_ms"] == 0 and time.monotonic() < until:
                time.sleep(0.005)
            self.assertGreater(runner.snapshot()["unrecoverable_age_ms"], 0)

            closer = Thread(target=runner.close, daemon=True)
            closer.start()
            until = time.monotonic() + 1
            while runner.snapshot()["state"] != "loop_down" and time.monotonic() < until:
                time.sleep(0.005)
            release_first.set()
            release_second.set()
            closer.join(timeout=1)
            self.assertFalse(closer.is_alive())

            time.sleep(0.4)
            self.assertFalse(fatal_called.is_set())
            self.assertEqual(runner.snapshot()["fatal_recovery_count"], 0)
        finally:
            release_first.set()
            release_second.set()
            first_released.wait(timeout=1)
            second_released.wait(timeout=1)
            if closer is not None:
                closer.join(timeout=1)
            runner.close()

    def test_request_racing_close_has_no_submission_or_lease_leak(self):
        response_started = Event()
        release_response = Event()
        submit_entered = Event()
        release_submit = Event()

        async def handler(_request):
            return httpx.Response(
                200,
                stream=_BlockingStream(response_started, release_response),
            )

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            ),
            cleanup_grace=0.05,
        )
        original_submit = asyncio.run_coroutine_threadsafe
        outcomes = []
        errors = []

        def delayed_submit(coroutine, loop):
            submit_entered.set()
            release_submit.wait(timeout=1)
            return original_submit(coroutine, loop)

        def make_request():
            try:
                outcomes.append(runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 1,
                ))
            except BaseException as exc:
                errors.append(exc)

        requester = Thread(target=make_request, daemon=True)
        closer = Thread(target=runner.close, daemon=True)
        started = time.monotonic()
        try:
            with patch(
                "app.integrations.kai_pricing.asyncio.run_coroutine_threadsafe",
                side_effect=delayed_submit,
            ):
                requester.start()
                self.assertTrue(submit_entered.wait(timeout=1))
                closer.start()
                # request() still owns the short state lock here; releasing the
                # submit boundary lets close win immediately afterwards.
                release_submit.set()
                release_response.set()
                requester.join(timeout=1)
                closer.join(timeout=1)

            self.assertFalse(requester.is_alive())
            self.assertFalse(closer.is_alive())
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(len(outcomes) + len(errors), 1)
            if errors:
                self.assertIsInstance(errors[0], KaiPricingError)
                self.assertIn(errors[0].code, {"upstream_error", "upstream_timeout"})
            snapshot = runner.snapshot()
            self.assertEqual(snapshot["state"], "loop_down")
            self.assertEqual(snapshot["pending"], 0)
            self.assertEqual(snapshot["active"], 0)
            self.assertEqual(snapshot["retired_pending"], 0)
            self.assertEqual(snapshot["retired_active"], 0)
        finally:
            release_submit.set()
            release_response.set()
            if requester.ident is not None:
                requester.join(timeout=1)
            if closer.ident is not None:
                closer.join(timeout=1)
            runner.close()

    def test_factory_backoff_expiry_allows_next_rebuild_to_succeed(self):
        close_started = Event()
        release_old = Event()
        old_released = Event()
        factory_lock = Lock()
        factory_calls = 0

        def client_factory():
            nonlocal factory_calls
            with factory_lock:
                factory_calls += 1
                call = factory_calls
            if call == 2:
                raise RuntimeError("one synthetic construction failure")

            async def handler(_request):
                if call == 1:
                    return httpx.Response(
                        200,
                        stream=_CancellationResistantCloseStream(
                            close_started,
                            release_old,
                            old_released,
                        ),
                    )
                return httpx.Response(200, json={"factory_call": call})

            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        runner = _AsyncHttpRunner(
            max_pending=1,
            client_factory=client_factory,
            cleanup_grace=0.05,
            watchdog_interval=0.01,
            restart_retry_seconds=0.25,
            fatal_recovery_threshold=10,
        )
        try:
            with self.assertRaises(KaiPricingError):
                runner.request(
                    "https://pricing.kai.test/v1/prices",
                    1024,
                    time.monotonic() + 0.15,
                )
            self.assertTrue(close_started.wait(timeout=1))

            until = time.monotonic() + 1
            while runner.snapshot()["restart_failure_count"] == 0 and time.monotonic() < until:
                time.sleep(0.005)
            after_failure = runner.snapshot()
            self.assertEqual(after_failure["restart_failure_count"], 1)
            self.assertEqual(after_failure["generation"], 1)
            self.assertGreater(after_failure["rebuild_backoff_remaining_ms"], 0)

            until = time.monotonic() + 1
            while runner.snapshot()["generation"] == 1 and time.monotonic() < until:
                time.sleep(0.005)
            recovered = runner.snapshot()
            self.assertEqual(recovered["generation"], 2)
            self.assertEqual(recovered["restart_count"], 1)
            self.assertEqual(recovered["restart_failure_count"], 1)
            self.assertEqual(recovered["rebuild_backoff_remaining_ms"], 0)
            with factory_lock:
                self.assertEqual(factory_calls, 3)

            payload, _size = runner.request(
                "https://pricing.kai.test/v1/prices",
                1024,
                time.monotonic() + 1,
            )
            self.assertEqual(payload, {"factory_call": 3})
        finally:
            release_old.set()
            old_released.wait(timeout=1)
            runner.close()


if __name__ == "__main__":
    unittest.main()
