import asyncio
import unittest
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.integrations.kai_pricing import KaiPricingError
from app.core.config import settings
from app.models.market_price import MarketCandleSyncStatus, MarketPriceCandle, MarketPriceSnapshot
from app.services.market_candle_sync import (
    CANDLE_RANGE_INTERVALS,
    CANDLE_RANGE_REFRESH_SECONDS,
    _identities,
    _pending_jobs,
    sync_market_candles,
)
from init_db import _migrate_market_candle_resolutions


class MarketCandleSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(self.engine)
        MarketPriceCandle.__table__.create(self.engine)
        MarketCandleSyncStatus.__table__.create(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        now = datetime(2026, 8, 22, 12, 0)
        db = self.session_factory()
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand", currency="CNY",
            min_price=Decimal("25"), p25_price=Decimal("25"), median_price=Decimal("25"),
            p75_price=Decimal("25"), max_price=Decimal("25"), min_price_cny=Decimal("25"),
            median_price_cny=Decimal("25"), max_price_cny=Decimal("25"), sample_count=8,
            available_gpu_count=0, fx_rate=Decimal("1"), fx_source="CNY native", fx_date="2026-08-22",
            data_quality="verified", signature="live", observed_at=now, fetched_at=now,
        ))
        db.commit()
        db.close()

    def test_worker_syncs_one_job_per_persisted_resolution(self):
        self.assertEqual(CANDLE_RANGE_INTERVALS, {
            "7d": 60 * 60,
            "30d": 4 * 60 * 60,
            "90d": 24 * 60 * 60,
        })

    def test_startup_candle_sync_uses_bounded_non_force_queue(self):
        from app.main import lifespan

        scheduled = []

        class SchedulerProbe:
            def __init__(self, **_kwargs):
                pass

            def add_job(self, function, trigger, **kwargs):
                scheduled.append((function, trigger, kwargs))

            def start(self):
                pass

            def shutdown(self):
                pass

        async def exercise_lifespan():
            with patch("app.main.BackgroundScheduler", SchedulerProbe), patch(
                "app.main.assert_sensitive_storage_secure",
            ), patch("app.main.assert_reward_configuration_safe"), patch(
                "app.main.assert_merchant_settlement_configuration_safe",
            ):
                async with lifespan(None):
                    pass

        asyncio.run(exercise_lifespan())
        startup = next(
            kwargs for _function, _trigger, kwargs in scheduled
            if kwargs.get("id") == "market_candle_startup_sync"
        )
        self.assertEqual(startup.get("kwargs"), {"force": False})

    def test_all_model_identities_are_eligible_and_scheduled_without_starvation(self):
        now = datetime(2026, 8, 29, 8, 0)
        db = self.session_factory()
        for index in range(40):
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model=f"GPU{index:02d}", gpu_variant="24GB",
                billing_mode="ondemand", currency="CNY",
                min_price=Decimal("5"), p25_price=Decimal("5"),
                median_price=Decimal("5"), p75_price=Decimal("5"), max_price=Decimal("5"),
                min_price_cny=Decimal("5"), median_price_cny=Decimal("5"),
                max_price_cny=Decimal("5"), sample_count=1, available_gpu_count=0,
                fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-29",
                data_quality="verified", signature=f"identity-{index}",
                observed_at=now, fetched_at=now,
            ))
        db.commit()
        db.close()

        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch.object(
            settings, "KAI_RANKING_MAX_PRODUCTS", 2,
        ), patch.object(settings, "MARKET_CANDLE_SYNC_MAX_JOBS", 4), patch(
            "app.services.market_candle_sync.utcnow", return_value=now,
        ):
            identities = _identities()
            first = _pending_jobs(identities, False)

            self.assertEqual(len(identities), 41)
            self.assertIn(("GPU39", "24GB"), identities)
            self.assertEqual(len(first), 4)
            self.assertEqual({range_name for _identity, range_name in first}, {"7d"})

            db = self.session_factory()
            for index, (identity, range_name) in enumerate(first):
                interval_seconds = CANDLE_RANGE_INTERVALS[range_name]
                start = now - timedelta(seconds=interval_seconds * (index + 2))
                db.add(MarketPriceCandle(
                    source="kai", gpu_model=identity[0], gpu_variant=identity[1],
                    billing_mode="ondemand", interval_seconds=interval_seconds,
                    start_time=start, end_time=start + timedelta(seconds=interval_seconds),
                    open_price_cny=Decimal("5"), high_price_cny=Decimal("5"),
                    low_price_cny=Decimal("5"), close_price_cny=Decimal("5"),
                    sample_count=1, observation_count=1, method="official",
                    data_quality="official", source_version="v1",
                    signature=f"scheduled-{index}", source_observed_at=now,
                    collected_at=now, updated_at=now,
                ))
            db.commit()
            db.close()

            second = _pending_jobs(identities, False)
            self.assertEqual(len(second), 4)
            self.assertTrue(set(first).isdisjoint(second))
        self.assertEqual(CANDLE_RANGE_REFRESH_SECONDS, {
            "7d": 10 * 60,
            "30d": 60 * 60,
            "90d": 6 * 60 * 60,
        })

    def payload(self, range_name: str, *, data_version: int = 7, price_shift: int = 0):
        start = datetime(2026, 8, 20)
        interval_seconds = CANDLE_RANGE_INTERVALS[range_name]
        step = timedelta(seconds=interval_seconds)
        return {
            "gpu_model": "H100",
            "gpu_variant": "80GB",
            "range": range_name,
            "bucket_seconds": interval_seconds,
            "method": "kai_official_ohlc",
            "data_quality": "official_historical_ohlc",
            "provenance": {
                "data_version": data_version,
                "as_of": "2026-08-22T12:00:00Z",
            },
            "candles": [{
                "start_time": (start + step * index).isoformat() + "Z",
                "end_time": (start + step * (index + 1)).isoformat() + "Z",
                "open_price_cny": 25 + price_shift + index,
                "high_price_cny": 26 + price_shift + index,
                "low_price_cny": 24 + price_shift + index,
                "close_price_cny": 25.5 + price_shift + index,
                "sample_count": 8,
                "observation_count": 8,
                "sources": ["kai"],
            } for index in range(2)],
        }

    def test_agent_persists_all_official_resolutions_idempotently(self):
        now = datetime(2026, 8, 29, 8, 0)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=now,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=lambda _model, _variant, range_name: self.payload(range_name),
        ) as fetch:
            first = sync_market_candles(force=True)
            second = sync_market_candles(force=True)

        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["inserted"], 6)
        self.assertEqual(first["models"], 1)
        self.assertEqual(first["ranges"], 3)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(
            Counter(call.args[2] for call in fetch.call_args_list),
            Counter({"7d": 2, "30d": 2, "90d": 2}),
        )
        db = self.session_factory()
        self.assertEqual(db.query(MarketPriceCandle).count(), 6)
        self.assertEqual(
            {row.interval_seconds for row in db.query(MarketPriceCandle).all()},
            {60 * 60, 4 * 60 * 60, 24 * 60 * 60},
        )
        self.assertEqual(
            db.query(MarketPriceCandle).filter(
                MarketPriceCandle.start_time == datetime(2026, 8, 20),
            ).count(),
            3,
        )
        status = db.query(MarketCandleSyncStatus).one()
        self.assertEqual(status.status, "ok")
        self.assertEqual(status.model_count, 1)
        self.assertEqual(status.candle_count, 6)
        db.close()

    def test_metadata_only_refresh_uses_bounded_bulk_reads_and_one_heartbeat(self):
        first_time = datetime(2026, 8, 29, 8, 0)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=first_time,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=lambda _model, _variant, range_name: self.payload(range_name, data_version=7),
        ):
            self.assertEqual(sync_market_candles(force=True)["status"], "ok")

        db = self.session_factory()
        before = {
            (row.interval_seconds, row.start_time): row.collected_at
            for row in db.query(MarketPriceCandle).all()
        }
        db.close()

        candle_selects = []

        def capture_select(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = statement.lower()
            if normalized.lstrip().startswith("select") and "market_price_candles_v2" in normalized:
                candle_selects.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture_select)
        second_time = first_time + timedelta(minutes=15)
        try:
            with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
                "app.services.market_candle_sync.utcnow", return_value=second_time,
            ), patch(
                "app.services.market_candle_sync.get_aggregated_candles",
                side_effect=lambda _model, _variant, range_name: self.payload(range_name, data_version=8),
            ):
                result = sync_market_candles(force=True)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_select)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["inserted"], 0)
        # One bounded window lookup per persisted resolution replaces the old
        # one-SELECT-per-candle write path.
        self.assertEqual(len(candle_selects), 3)
        db = self.session_factory()
        rows = db.query(MarketPriceCandle).order_by(
            MarketPriceCandle.interval_seconds,
            MarketPriceCandle.start_time,
        ).all()
        for interval_seconds in CANDLE_RANGE_INTERVALS.values():
            interval_rows = [row for row in rows if row.interval_seconds == interval_seconds]
            self.assertEqual(interval_rows[0].collected_at, before[(interval_seconds, interval_rows[0].start_time)])
            self.assertEqual(interval_rows[-1].collected_at, second_time)
            # The containing live version changed, but identical OHLC history
            # did not receive a full-window metadata rewrite.
            self.assertEqual({row.source_version for row in interval_rows}, {"7"})
        db.close()

    def test_single_range_failure_preserves_last_successful_resolution(self):
        first_time = datetime(2026, 8, 29, 8, 0)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=first_time,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=lambda _model, _variant, range_name: self.payload(range_name),
        ):
            self.assertEqual(sync_market_candles(force=True)["status"], "ok")

        db = self.session_factory()
        old_four_hour = db.query(MarketPriceCandle).filter(
            MarketPriceCandle.interval_seconds == 4 * 60 * 60,
            MarketPriceCandle.start_time == datetime(2026, 8, 20),
        ).one()
        old_close = old_four_hour.close_price_cny
        old_collected_at = old_four_hour.collected_at
        db.close()

        def partial_fetch(_model, _variant, range_name):
            if range_name == "30d":
                raise KaiPricingError("upstream_timeout")
            return self.payload(range_name, data_version=8, price_shift=10)

        second_time = first_time + timedelta(minutes=15)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=second_time,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=partial_fetch,
        ):
            result = sync_market_candles(force=True)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["ranges"], 2)
        db = self.session_factory()
        self.assertEqual(db.query(MarketPriceCandle).count(), 6)
        retained = db.query(MarketPriceCandle).filter(
            MarketPriceCandle.interval_seconds == 4 * 60 * 60,
            MarketPriceCandle.start_time == datetime(2026, 8, 20),
        ).one()
        refreshed = db.query(MarketPriceCandle).filter(
            MarketPriceCandle.interval_seconds == 60 * 60,
            MarketPriceCandle.start_time == datetime(2026, 8, 20),
        ).one()
        self.assertEqual(retained.close_price_cny, old_close)
        self.assertEqual(retained.collected_at, old_collected_at)
        self.assertEqual(refreshed.close_price_cny, Decimal("35.5"))
        status = db.query(MarketCandleSyncStatus).one()
        self.assertEqual(status.status, "partial")
        self.assertEqual(status.last_error, "upstream_timeout")
        db.close()

    def test_non_force_sync_skips_fresh_resolutions_and_only_fetches_due_range(self):
        collected_at = datetime(2026, 8, 29, 8, 0)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=collected_at,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=lambda _model, _variant, range_name: self.payload(range_name),
        ):
            sync_market_candles(force=True)

        db = self.session_factory()
        status = db.query(MarketCandleSyncStatus).one()
        status.last_attempt_at = collected_at
        db.commit()
        db.close()

        five_minutes_later = collected_at + timedelta(minutes=5)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=five_minutes_later,
        ), patch("app.services.market_candle_sync.get_aggregated_candles") as fetch:
            result = sync_market_candles(force=False)
        self.assertEqual(result["status"], "not_due")
        fetch.assert_not_called()

        eleven_minutes_later = collected_at + timedelta(minutes=11)
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.utcnow", return_value=eleven_minutes_later,
        ), patch(
            "app.services.market_candle_sync.get_aggregated_candles",
            side_effect=lambda _model, _variant, range_name: self.payload(range_name),
        ) as fetch:
            result = sync_market_candles(force=False)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ranges"], 1)
        self.assertEqual([call.args[2] for call in fetch.call_args_list], ["7d"])

    def test_additive_migration_copies_legacy_rows_and_keeps_old_table(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE market_price_candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source VARCHAR(24) NOT NULL,
                    gpu_model VARCHAR(64) NOT NULL,
                    gpu_variant VARCHAR(64) NOT NULL,
                    billing_mode VARCHAR(24) NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    open_price_cny NUMERIC(18, 6) NOT NULL,
                    high_price_cny NUMERIC(18, 6) NOT NULL,
                    low_price_cny NUMERIC(18, 6) NOT NULL,
                    close_price_cny NUMERIC(18, 6) NOT NULL,
                    sample_count INTEGER NOT NULL,
                    observation_count INTEGER NOT NULL,
                    method VARCHAR(96) NOT NULL,
                    data_quality VARCHAR(32) NOT NULL,
                    source_version VARCHAR(64),
                    signature VARCHAR(64) NOT NULL,
                    source_observed_at DATETIME,
                    collected_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_market_price_candle_identity UNIQUE (
                        source, gpu_model, gpu_variant, billing_mode, start_time
                    )
                )
            """))
            conn.execute(text("""
                INSERT INTO market_price_candles (
                    source, gpu_model, gpu_variant, billing_mode,
                    start_time, end_time,
                    open_price_cny, high_price_cny, low_price_cny, close_price_cny,
                    sample_count, observation_count, method, data_quality,
                    source_version, signature, source_observed_at, collected_at, updated_at
                ) VALUES (
                    'kai', 'H100', '80GB', 'ondemand',
                    '2026-08-20 00:00:00', '2026-08-20 04:00:00',
                    25, 26, 24, 25.5,
                    8, 8, 'official_ohlc', 'official',
                    '7', 'legacy-four-hour', '2026-08-22 12:00:00',
                    '2026-08-22 12:00:00', '2026-08-22 12:00:00'
                )
            """))

        self.assertEqual(_migrate_market_candle_resolutions(engine), 1)
        self.assertEqual(_migrate_market_candle_resolutions(engine), 0)
        self.assertIn("market_price_candles", inspect(engine).get_table_names())
        self.assertIn("market_price_candles_v2", inspect(engine).get_table_names())
        db = sessionmaker(bind=engine)()
        copied = db.query(MarketPriceCandle).one()
        self.assertEqual(copied.interval_seconds, 4 * 60 * 60)
        db.add(MarketPriceCandle(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            interval_seconds=60 * 60,
            start_time=datetime(2026, 8, 20), end_time=datetime(2026, 8, 20, 1),
            open_price_cny=Decimal("25"), high_price_cny=Decimal("26"),
            low_price_cny=Decimal("24"), close_price_cny=Decimal("25.5"),
            sample_count=8, observation_count=8, method="official_ohlc",
            data_quality="official", source_version="8", signature="new-one-hour",
            source_observed_at=datetime(2026, 8, 22, 12),
            collected_at=datetime(2026, 8, 22, 12), updated_at=datetime(2026, 8, 22, 12),
        ))
        db.commit()
        self.assertEqual(db.query(MarketPriceCandle).count(), 2)
        self.assertEqual(
            db.execute(text("SELECT COUNT(*) FROM market_price_candles")).scalar_one(),
            1,
        )
        db.close()


if __name__ == "__main__":
    unittest.main()
