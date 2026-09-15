import time
import unittest
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event, Lock
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.market_price import MarketHistoryPoint
from app.routers.market import (
    MARKET_LATEST_CACHE_SECONDS,
    MARKET_SUMMARY_CACHE_SECONDS,
    _MARKET_RESPONSE_CACHE,
    _summary_history_metrics,
    latest_prices,
)
from app.services.market_history_sync import select_market_history_bulk
from app.services.sync_ttl_cache import SyncTtlCache, SyncTtlCacheOverloadedError


class MarketPerformanceTests(unittest.TestCase):
    def test_nginx_compresses_large_market_json_responses(self):
        repository = Path(__file__).resolve().parents[3]
        nginx = (repository / "infra" / "kai-nginx.conf").read_text(encoding="utf-8")

        self.assertIn("gzip on;", nginx)
        self.assertIn("gzip_min_length 1024;", nginx)
        self.assertIn("gzip_types application/json", nginx)

    def test_summary_prefers_official_candles_without_snapshot_rescan(self):
        identity = ("RTX4090", "24GB")
        official = {identity: {"history_provenance": {"kind": "official_historical_ohlc"}}}

        with patch("app.routers.market._kai_history_metrics", return_value=official) as candle_metrics, patch(
            "app.routers.market._seven_day_metrics",
        ) as snapshot_metrics:
            result = _summary_history_metrics(
                self,
                datetime(2026, 9, 15),
                [identity],
                {"kai"},
            )

        self.assertEqual(result, official)
        candle_metrics.assert_called_once_with(self, {identity})
        snapshot_metrics.assert_not_called()
        self.assertGreaterEqual(MARKET_SUMMARY_CACHE_SECONDS, 300)

    def test_summary_limits_snapshot_fallback_to_missing_identities(self):
        official_identity = ("RTX4090", "24GB")
        missing_identity = ("H100", "80GB")
        official_metric = {"history_provenance": {"kind": "official_historical_ohlc"}}
        fallback_metric = {"history_provenance": {"kind": "snapshot_fallback"}}

        with patch(
            "app.routers.market._kai_history_metrics",
            return_value={official_identity: official_metric},
        ), patch(
            "app.routers.market._seven_day_metrics",
            return_value={missing_identity: fallback_metric},
        ) as snapshot_metrics:
            result = _summary_history_metrics(
                self,
                datetime(2026, 9, 15),
                [official_identity, missing_identity],
                {"kai"},
            )

        self.assertEqual(result[official_identity], official_metric)
        self.assertEqual(result[missing_identity], fallback_metric)
        snapshot_metrics.assert_called_once_with(
            self,
            datetime(2026, 9, 15),
            {"kai"},
            {missing_identity},
        )

    def test_duplicate_market_requests_share_one_loader(self):
        cache = SyncTtlCache(max_entries=8)
        calls = 0
        counter_lock = Lock()

        def loader():
            nonlocal calls
            with counter_lock:
                calls += 1
            time.sleep(0.04)
            return {"candles": [1, 2, 3]}

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(
                lambda _: cache.get_or_load(("RTX4090", "24GB", "7d"), 60, loader),
                range(24),
            ))

        self.assertEqual(calls, 1)
        self.assertTrue(all(result == {"candles": [1, 2, 3]} for result in results))

    def test_cache_ttl_lru_failure_flight_and_snapshot_isolation(self):
        clock = [0.0]
        cache = SyncTtlCache(max_entries=2, clock=lambda: clock[0])
        loads = 0
        source = {"items": [{"price": 1}]}

        def load_source():
            nonlocal loads
            loads += 1
            return source

        first = cache.get_or_load("a", 8, load_source)
        source["items"][0]["price"] = 99
        first["items"].append({"price": 2})
        self.assertEqual(cache.get_or_load("a", 8, lambda: {}), {"items": [{"price": 1}]})
        clock[0] = 7.999
        self.assertEqual(cache.get_or_load("a", 8, lambda: {}), {"items": [{"price": 1}]})
        clock[0] = 8.001

        def load_expired():
            nonlocal loads
            loads += 1
            return {"items": []}

        self.assertEqual(cache.get_or_load("a", 8, load_expired), {"items": []})
        self.assertEqual(loads, 2)

        lru_cache = SyncTtlCache(max_entries=2, clock=lambda: clock[0])
        lru_cache.get_or_load("a", 8, lambda: {"key": "a"})
        lru_cache.get_or_load("b", 8, lambda: {"key": "b"})
        lru_cache.get_or_load("a", 8, lambda: {})
        lru_cache.get_or_load("c", 8, lambda: {"key": "c"})
        b_loads = 0

        def load_b():
            nonlocal b_loads
            b_loads += 1
            return {"key": "b-new"}

        self.assertEqual(lru_cache.get_or_load("b", 8, load_b), {"key": "b-new"})
        self.assertEqual(b_loads, 1)

        failure_cache = SyncTtlCache(max_entries=2)
        start = Barrier(13)
        calls = 0
        calls_lock = Lock()

        def failing_loader():
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.05)
            raise RuntimeError("database unavailable")

        def failing_read(_):
            start.wait()
            try:
                failure_cache.get_or_load("same", 8, failing_loader)
            except RuntimeError as error:
                return str(error)
            return "unexpected success"

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(failing_read, index) for index in range(12)]
            start.wait()
            errors = [future.result() for future in futures]
        self.assertEqual(calls, 1)
        self.assertEqual(errors, ["database unavailable"] * 12)
        self.assertEqual(failure_cache.get_or_load("same", 8, lambda: {"ok": True}), {"ok": True})

    def test_distinct_key_flood_has_bounded_loaders_and_queue(self):
        cache = SyncTtlCache(
            max_entries=16,
            max_concurrent_loads=3,
            max_pending_loads=4,
        )
        start = Barrier(9)
        release_loaders = Event()
        activity_lock = Lock()
        active_loaders = 0
        max_active_loaders = 0

        def loader(key):
            nonlocal active_loaders, max_active_loaders
            with activity_lock:
                active_loaders += 1
                max_active_loaders = max(max_active_loaders, active_loaders)
            try:
                self.assertTrue(release_loaders.wait(timeout=2))
                return {"key": key}
            finally:
                with activity_lock:
                    active_loaders -= 1

        def read(key):
            start.wait()
            try:
                value = cache.get_or_load(key, 60, lambda: loader(key))
            except SyncTtlCacheOverloadedError:
                return "overloaded", key, None
            return "loaded", key, value

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(read, key) for key in range(8)]
            start.wait()
            completed, _ = wait(futures, timeout=2, return_when=FIRST_COMPLETED)
            self.assertEqual(len(completed), 1)
            self.assertEqual(next(iter(completed)).result()[0], "overloaded")
            release_loaders.set()
            results = [future.result(timeout=2) for future in futures]

        loaded = [result for result in results if result[0] == "loaded"]
        overloaded = [result for result in results if result[0] == "overloaded"]
        self.assertEqual(len(loaded), 7)
        self.assertEqual(len(overloaded), 1)
        self.assertEqual(max_active_loaders, 3)
        self.assertEqual(active_loaders, 0)
        self.assertTrue(all(result[2] == {"key": result[1]} for result in loaded))

        overloaded_key = overloaded[0][1]
        self.assertEqual(
            cache.get_or_load(overloaded_key, 60, lambda: {"key": overloaded_key}),
            {"key": overloaded_key},
        )

    def test_distinct_key_queue_wait_is_bounded(self):
        cache = SyncTtlCache(
            max_entries=4,
            max_concurrent_loads=1,
            max_pending_loads=1,
            max_queue_wait_seconds=0.02,
        )
        loader_started = Event()
        release_loader = Event()

        def blocked_loader():
            loader_started.set()
            self.assertTrue(release_loader.wait(timeout=2))
            return {"key": "active"}

        with ThreadPoolExecutor(max_workers=2) as executor:
            active = executor.submit(cache.get_or_load, "active", 60, blocked_loader)
            self.assertTrue(loader_started.wait(timeout=1))
            started_at = time.monotonic()
            with self.assertRaisesRegex(SyncTtlCacheOverloadedError, "wait timed out"):
                cache.get_or_load("waiting", 60, lambda: {"key": "waiting"})
            self.assertLess(time.monotonic() - started_at, 0.5)
            release_loader.set()
            self.assertEqual(active.result(timeout=2), {"key": "active"})

        self.assertEqual(
            cache.get_or_load("waiting", 60, lambda: {"key": "waiting"}),
            {"key": "waiting"},
        )

    def test_latest_endpoint_coalesces_each_normalized_identity(self):
        counts: dict[tuple[str, str | None], int] = {}
        counts_lock = Lock()

        def build_payload(model, variant, _sources, _db):
            key = (model, variant)
            with counts_lock:
                counts[key] = counts.get(key, 0) + 1
            time.sleep(0.04)
            return {
                "server_time": "2026-09-11T00:00:00Z",
                "next_refresh_in": 300,
                "gpu_model": model,
                "gpu_variant": variant or "80GB",
                "summary": {"median_price_card_hours": 1},
                "items": [],
                "requested_source_states": {"kai": "live"},
                "excluded_sources": [],
            }

        with TemporaryDirectory() as folder:
            database_path = Path(folder) / "market.db"
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            session_factory = sessionmaker(bind=engine)

            def read(identity):
                model, variant = identity
                with session_factory() as db:
                    return latest_prices(model, variant, "kai", db)["data"]

            identities = [("H100", "80GB")] * 25 + [("RTX4090", "24GB")] * 25
            _MARKET_RESPONSE_CACHE.clear()
            try:
                with patch("app.routers.market._latest_prices_payload", side_effect=build_payload):
                    with ThreadPoolExecutor(max_workers=50) as executor:
                        results = list(executor.map(read, identities))
                    self.assertEqual(counts, {("H100", "80GB"): 1, ("RTX4090", "24GB"): 1})
                    self.assertEqual([item["gpu_model"] for item in results].count("H100"), 25)
                    self.assertEqual([item["gpu_model"] for item in results].count("RTX4090"), 25)
                    self.assertEqual(MARKET_LATEST_CACHE_SECONDS, 8)
            finally:
                _MARKET_RESPONSE_CACHE.clear()
                engine.dispose()

    def test_bulk_history_selection_uses_one_query_for_many_models(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 0, 0)
        for model, variant, base in (("RTX4090", "24GB", 1), ("RTX5070TI", "16GB", 2)):
            for day in range(7):
                price = Decimal(base) + Decimal(day) / Decimal("100")
                db.add(MarketHistoryPoint(
                    dataset_source="hf_gpu_prices",
                    upstream_provider="vast",
                    gpu_model=model,
                    gpu_variant=variant,
                    billing_mode="ondemand",
                    currency="USD",
                    low_price=price,
                    representative_price=price,
                    high_price=price,
                    low_price_cny=price,
                    representative_price_cny=price,
                    high_price_cny=price,
                    sample_count=10,
                    available_gpu_count=10,
                    fx_rate=Decimal("1"),
                    fx_source="test",
                    fx_date="2026-08-18",
                    data_quality="external_reference",
                    index_method="daily_test_median",
                    source_url="https://example.test/history",
                    license_name="CC BY 4.0",
                    dataset_version="test",
                    signature=f"{model}-{day}",
                    observed_at=start + timedelta(days=day),
                    collected_at=start + timedelta(days=6),
                ))
        db.commit()

        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        selected = select_market_history_bulk(
            db,
            {("RTX4090", "24GB"), ("RTX5070TI", "16GB")},
            start,
            start + timedelta(days=7),
        )
        event.remove(engine, "before_cursor_execute", count_selects)

        self.assertEqual(select_count, 1)
        self.assertEqual(set(selected), {("RTX4090", "24GB"), ("RTX5070TI", "16GB")})
        self.assertTrue(all(item.available for item in selected.values()))
        db.close()


if __name__ == "__main__":
    unittest.main()
