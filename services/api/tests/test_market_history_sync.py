import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import duckdb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.utils.response import BizError
from app.models.market_price import (
    MarketCandleSyncStatus,
    MarketHistoryPoint,
    MarketPriceCandle,
    MarketPriceSnapshot,
    MarketSourceStatus,
)
from app.routers.market import (
    MARKET_CANDLE_CONFIG,
    _historical_metric,
    _price_candles_payload,
    _range_coverage_requirements,
    price_history,
    price_candles,
)
from app.services.gpu_catalog import gpu_variant_aliases, normalize_gpu_variant
from app.services.market_history_sync import (
    HF_SOURCE,
    OFFICIAL_SOURCE,
    HistorySourceFailure,
    _fetch_vast_official,
    _store_points,
    parse_hf_parquet,
    parse_vast_official_history,
    select_market_history,
)


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response


class MarketHistorySyncTests(unittest.TestCase):
    def test_vast_official_response_parses_known_model_vram_and_available_median(self):
        now = datetime(2026, 8, 18, 8, 0)
        payload = {
            "gpus": {
                "RTX 4090": {
                    "pricing": {
                        "timestamps": [1_776_499_200],
                        "avail_p10": [0.30],
                        "avail_median": [0.35],
                        "avail_p90": [0.40],
                        "rented_median": [9.99],
                    }
                }
            }
        }
        rows = parse_vast_official_history(payload, now, (Decimal("7"), "test fx", "2026-08-18"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gpu_model"], "RTX4090")
        self.assertEqual(rows[0]["gpu_variant"], "24GB")
        self.assertEqual(rows[0]["representative_price"], Decimal("0.350000"))
        self.assertEqual(rows[0]["representative_price_cny"], Decimal("2.450000"))
        self.assertEqual(rows[0]["data_quality"], "official")

    def test_vast_history_fetch_is_retired_before_any_network_access(self):
        with self.assertRaises(HistorySourceFailure) as captured:
            _fetch_vast_official(
                _Client(_Response(200, {"unexpected": "must not be read"})),
                datetime(2026, 8, 11),
                datetime(2026, 8, 18),
            )
        self.assertEqual(captured.exception.code, "history_source_disabled")

    def test_hf_parser_filters_exact_vast_ondemand_rows_and_counts_gpus_once(self):
        with tempfile.TemporaryDirectory() as folder:
            parquet = Path(folder) / "snapshot.parquet"
            connection = duckdb.connect(database=":memory:")
            connection.execute("""
                CREATE TABLE prices AS SELECT * FROM (VALUES
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'a', 'RTX4090', 2, 24, 0.40, false, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'b', 'RTX4090', 4, 24, 0.80, false, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'c', 'RTX4090', 1, 24, 0.21, false, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'outlier', 'RTX4090', 1, 24, 5.00, false, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'spot', 'RTX4090', 10, 24, 0.10, true, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'bad', 'RTX4090', 10, 24, 0.10, false, true, 'bad'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'other', 'other', 'RTX4090', 10, 24, 0.10, false, true, 'ok')
                ) AS t(timestamp, provider, instance_type, gpu_type, gpu_count, gpu_memory_gb,
                       price_per_hour, is_spot, available, quality)
            """)
            connection.execute("COPY prices TO ? (FORMAT PARQUET)", [str(parquet)])
            connection.close()

            with patch("app.services.market_history_sync._cache_root", return_value=Path(folder)):
                rows = parse_hf_parquet(
                    [parquet],
                    "test-revision",
                    datetime(2026, 8, 18),
                    (Decimal("7"), "test fx", "2026-08-18"),
                    provider_filter={"vastai"},
                )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gpu_model"], "RTX4090")
        self.assertEqual(rows[0]["gpu_variant"], "24GB")
        self.assertEqual(rows[0]["sample_count"], 3)
        self.assertEqual(rows[0]["available_gpu_count"], 7)
        self.assertEqual(rows[0]["representative_price"], Decimal("0.200000"))
        self.assertEqual(rows[0]["data_quality"], "external_reference")
        self.assertEqual(rows[0]["license_name"], "CC BY 4.0")

    def test_complete_official_series_is_preferred_without_mixing_hf(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 8, 0)

        def point(source, day, price, quality):
            value = Decimal(price)
            return MarketHistoryPoint(
                dataset_source=source, upstream_provider="vast", gpu_model="RTX4090", gpu_variant="24GB",
                billing_mode="ondemand", currency="USD", low_price=value, representative_price=value,
                high_price=value, low_price_cny=value, representative_price_cny=value, high_price_cny=value,
                sample_count=1, available_gpu_count=1, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality=quality, index_method="test", source_url="https://example.test",
                license_name="test", dataset_version="v1", signature=f"{source}-{day}",
                observed_at=start + timedelta(days=day), collected_at=start + timedelta(days=day),
            )

        for day in range(7):
            db.add(point(HF_SOURCE, day, str(Decimal("1") + Decimal(day) / 100), "external_reference"))
            db.add(point(OFFICIAL_SOURCE, day, str(Decimal("2") + Decimal(day) / 100), "official"))
        db.commit()
        selected = select_market_history(db, "RTX4090", "24GB", start, start + timedelta(days=7))
        self.assertIsNotNone(selected)
        self.assertTrue(selected.available)
        self.assertEqual(selected.day_count, 7)
        self.assertEqual({row.dataset_source for row in selected.points}, {OFFICIAL_SOURCE})
        self.assertEqual(selected.change_7d_pct, 3.0)
        db.close()

    def test_exact_single_provider_market_reference_is_used_when_vast_is_absent(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 8, 0)
        for day in range(7):
            value = Decimal("3") + Decimal(day) / Decimal("100")
            db.add(MarketHistoryPoint(
                dataset_source=HF_SOURCE, upstream_provider="runpod", gpu_model="A100", gpu_variant="80GB",
                billing_mode="ondemand", currency="USD", low_price=value, representative_price=value,
                high_price=value, low_price_cny=value, representative_price_cny=value, high_price_cny=value,
                sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="external_reference", index_method="runpod_reference",
                source_url="https://example.test", license_name="CC BY 4.0", dataset_version="v1",
                signature=f"runpod-{day}", observed_at=start + timedelta(days=day), collected_at=start,
            ))
        db.commit()

        selected = select_market_history(db, "A100", "80GB", start, start + timedelta(days=7))
        self.assertIsNotNone(selected)
        self.assertTrue(selected.available)
        self.assertEqual({row.upstream_provider for row in selected.points}, {"runpod"})
        self.assertEqual(selected.provenance["upstream_provider"], "runpod")
        db.close()

    def test_kai_official_candles_are_not_spliced_with_legacy_vast_history(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 8, 0)
        now = datetime(2026, 8, 18, 8, 0)
        for day in range(7):
            value = Decimal("2") + Decimal(day) / Decimal("100")
            db.add(MarketHistoryPoint(
                dataset_source=HF_SOURCE, upstream_provider="vast", gpu_model="RTX4090", gpu_variant="24GB",
                billing_mode="ondemand", currency="USD", low_price=value, representative_price=value,
                high_price=value, low_price_cny=value, representative_price_cny=value, high_price_cny=value,
                sample_count=3, available_gpu_count=3, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="external_reference", index_method="test",
                source_url="https://example.test", license_name="CC BY 4.0", dataset_version="v1",
                signature=f"history-{day}", observed_at=start + timedelta(days=day),
                collected_at=start + timedelta(days=day),
            ))
        live = Decimal("99")
        db.add(MarketPriceSnapshot(
            source="vast", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand", currency="USD",
            min_price=live, p25_price=live, median_price=live, p75_price=live, max_price=live,
            min_price_cny=live, median_price_cny=live, max_price_cny=live, sample_count=10,
            available_gpu_count=10, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="live", observed_at=now, fetched_at=now,
        ))
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand", currency="CNY",
            min_price=Decimal("2.06"), p25_price=Decimal("2.06"), median_price=Decimal("2.06"),
            p75_price=Decimal("2.06"), max_price=Decimal("2.06"), min_price_cny=Decimal("2.06"),
            median_price_cny=Decimal("2.06"), max_price_cny=Decimal("2.06"), sample_count=1,
            available_gpu_count=0, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="kai-live", observed_at=now, fetched_at=now,
        ))
        for index in range(168):
            candle_open = Decimal("2.0") + Decimal("0.06") * Decimal(index) / Decimal("167")
            candle_close = candle_open
            candle_start = start + timedelta(hours=index)
            db.add(MarketPriceCandle(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                interval_seconds=60 * 60,
                start_time=candle_start, end_time=candle_start + timedelta(hours=1),
                open_price_cny=candle_open, high_price_cny=candle_close + Decimal("0.005"),
                low_price_cny=candle_open - Decimal("0.005"), close_price_cny=candle_close,
                sample_count=1, observation_count=1, method="official_ohlc", data_quality="official",
                source_version="v1", signature=f"stored-candle-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.add(MarketCandleSyncStatus(
            source="kai", status="ok", refresh_seconds=300, model_count=1, candle_count=168,
            last_attempt_at=now, last_success_at=now,
        ))
        db.commit()
        with patch("app.routers.market.utcnow", return_value=now):
            metric = _historical_metric(db, now, "RTX4090", "24GB")
            payload = price_candles("RTX4090", "24GB", "7d", "kai", "ondemand", db)["data"]

        self.assertEqual(metric["change_7d_pct"], 3.0)
        self.assertEqual(metric["range_low_cny"], 2.0)
        self.assertEqual(metric["range_high_cny"], 2.06)
        self.assertEqual(payload["history_status"], "available")
        self.assertEqual(payload["curve_status"], "full")
        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(len(payload["candles"]), 168)
        self.assertEqual(payload["expected_bucket_count"], 168)
        self.assertEqual(payload["observed_bucket_coverage_ratio"], 1.0)
        self.assertEqual(payload["coverage_span_hours"], 168.0)
        self.assertEqual(payload["provenance"]["history_as_of"], "2026-08-18T08:00:00Z")
        self.assertEqual(payload["provenance"]["history_lag_seconds"], 0)
        self.assertEqual(payload["latest_live_price_cny"], 2.06)
        self.assertFalse(payload["provenance"]["live_component_included"])
        self.assertFalse(payload["latest_live_comparable_to_history"])
        self.assertLess(max(candle["high_price_cny"] for candle in payload["candles"]), 3)
        self.assertEqual({source for candle in payload["candles"] for source in candle["sources"]}, {"kai"})
        db.close()

    def test_seven_day_curve_prefers_dense_contiguous_real_hourly_candles(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        start = now - timedelta(days=7)

        # A recent 85%-plus contiguous hourly suffix is dense enough to use
        # without filling any missing bucket.
        for index in range(24, 168):
            observed = start + timedelta(hours=index)
            value = Decimal("5") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-{index}", observed_at=observed, fetched_at=observed,
            ))
        for day in range(7):
            value = Decimal("99") + Decimal(day)
            candle_start = start + timedelta(days=day)
            db.add(MarketPriceCandle(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                start_time=candle_start, end_time=candle_start + timedelta(days=1),
                open_price_cny=value, high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=1, observation_count=1, method="official_ohlc", data_quality="official",
                source_version="v1", signature=f"stored-{day}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "RTX4090", "24GB", "7d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(payload["tick_seconds"], 15 * 60)
        self.assertGreaterEqual(len(payload["candles"]), 143)
        self.assertEqual(payload["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(payload["provenance"]["kind"], "direct_observation")
        self.assertFalse(payload["is_interpolated"])
        self.assertLess(max(candle["high_price_cny"] for candle in payload["candles"]), 7)
        db.close()

    def test_seven_day_curve_falls_back_when_latest_hourly_series_has_a_gap(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        start = now - timedelta(days=7)

        # There are more than 143 real observations in total, but the gap
        # leaves only eleven consecutive buckets at the latest edge.
        for index in list(range(156)) + list(range(157, 168)):
            observed = start + timedelta(hours=index)
            value = Decimal("5") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-gap-{index}", observed_at=observed, fetched_at=observed,
            ))
        for index in range(168):
            value = Decimal("20") + Decimal(index) / Decimal("100")
            candle_start = start + timedelta(hours=index)
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60,
                start_time=candle_start, end_time=candle_start + timedelta(hours=1),
                open_price_cny=value, high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=1, observation_count=1, method="official_ohlc", data_quality="official",
                source_version="v1", signature=f"stored-gap-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "7d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(len(payload["candles"]), 168)
        self.assertEqual(payload["method"], "official_ohlc")
        self.assertEqual(payload["provenance"]["kind"], "stored_official_historical_ohlc")
        self.assertGreaterEqual(min(candle["low_price_cny"] for candle in payload["candles"]), 20)
        db.close()

    def test_stored_window_stops_at_gap_and_reports_real_coverage(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("25"), p25_price=Decimal("25"), median_price=Decimal("25"),
            p75_price=Decimal("25"), max_price=Decimal("25"), min_price_cny=Decimal("25"),
            median_price_cny=Decimal("25"), max_price_cny=Decimal("25"), sample_count=8,
            available_gpu_count=0, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="gap-live", observed_at=now, fetched_at=now,
        ))
        starts = [now - timedelta(hours=24 - index) for index in range(13)]
        starts += [now - timedelta(hours=10 - index) for index in range(10)]
        for index, candle_start in enumerate(starts):
            value = Decimal("20") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=8, observation_count=8, method="official_hourly", data_quality="official",
                source_version="v1", signature=f"stored-window-gap-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(len(payload["candles"]), 10)
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["expected_bucket_count"], 24)
        self.assertEqual(payload["coverage_span_hours"], 10.0)
        self.assertAlmostEqual(payload["observed_bucket_coverage_ratio"], 10 / 24, places=4)
        db.close()

    def test_snapshot_coverage_requirements_scale_with_requested_range(self):
        expected = {
            timedelta(hours=1): (1, 0.85),
            timedelta(hours=6): (1, 5.1),
            timedelta(hours=24): (1, 20.4),
            timedelta(days=7): (6, 142.8),
            timedelta(days=30): (26, 612.0),
            timedelta(days=90): (77, 1836.0),
        }
        for duration, (days, hours) in expected.items():
            with self.subTest(duration=duration):
                actual_days, actual_hours = _range_coverage_requirements(duration)
                self.assertEqual(actual_days, days)
                self.assertAlmostEqual(actual_hours, hours)

    def test_public_candle_ranges_use_progressive_real_bucket_widths(self):
        expected = {
            "1h": 5 * 60,
            "3h": 15 * 60,
            "6h": 15 * 60,
            "24h": 60 * 60,
            "7d": 60 * 60,
            "30d": 4 * 60 * 60,
            "90d": 24 * 60 * 60,
        }
        self.assertEqual(
            {range_name: config[1] for range_name, config in MARKET_CANDLE_CONFIG.items()},
            expected,
        )

    def test_one_hour_uses_real_five_minute_publications_without_filling_gaps(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for index in range(13):
            observed = now - timedelta(minutes=60 - index * 5)
            value = Decimal("5") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-1h-{index}", observed_at=observed, fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "RTX4090", "24GB", "1h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["requested_bucket_seconds"], 5 * 60)
        self.assertEqual(payload["bucket_seconds"], 5 * 60)
        self.assertEqual(payload["tick_seconds"], 5 * 60)
        self.assertEqual(len(payload["candles"]), 12)
        self.assertEqual(sum(item["observation_count"] for item in payload["candles"]), 12)
        self.assertFalse(payload["is_interpolated"])
        self.assertEqual(payload["resolution_status"], "requested")
        db.close()

    def test_three_hour_range_is_supported_by_history_and_fifteen_minute_candles(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketSourceStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for index in range(37):
            observed = now - timedelta(minutes=180 - index * 5)
            value = Decimal("5") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-3h-{index}", observed_at=observed, fetched_at=observed,
            ))
        db.add(MarketSourceStatus(
            source="kai", enabled=True, status="ok", refresh_seconds=300,
            sample_count=4, last_attempt_at=now, last_success_at=now,
        ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            candle_payload = _price_candles_payload(
                "RTX4090", "24GB", "3h", "kai", "ondemand", db,
            )
            history_payload = price_history(
                "RTX4090", "24GB", "3h", "kai", db,
            )["data"]

        self.assertEqual(candle_payload["bucket_seconds"], 15 * 60)
        self.assertEqual(len(candle_payload["candles"]), 12)
        self.assertEqual(candle_payload["history_coverage_status"], "complete")
        self.assertEqual(history_payload["range"], "3h")
        self.assertEqual(history_payload["series"][0]["curve_status"], "full")
        self.assertEqual(len(history_payload["series"][0]["points"]), 37)
        db.close()

    def test_twenty_three_sparse_hourly_observations_do_not_claim_complete_twenty_four_hours(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for index in range(23):
            observed = now - timedelta(hours=22 - index)
            value = Decimal("5") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-24h-{index}", observed_at=observed, fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "RTX4090", "24GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["history_status"], "partial_history")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["expected_bucket_count"], 24)
        self.assertLess(payload["observed_tick_coverage_ratio"], 0.1)
        self.assertAlmostEqual(payload["coverage_span_hours"], 22.0)
        db.close()

    def test_twenty_four_hour_dense_five_minute_publications_form_twenty_four_real_hourly_candles(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 25)
        first_observation = now - timedelta(hours=24)
        ticks_by_hour: dict[datetime, list[Decimal]] = {}

        # Real KAI publications cover the full rolling day at five-minute
        # cadence. The current 08:00 hour is deliberately still in progress.
        for index in range(24 * 12 + 1):
            observed = first_observation + timedelta(minutes=index * 5)
            value = Decimal("30") + Decimal(index) / Decimal("1000")
            hour_start = observed.replace(minute=0, second=0, microsecond=0)
            ticks_by_hour.setdefault(hour_start, []).append(value)
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"dense-24h-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))

        # Matching closed official hourly history is present as a consistency
        # reference. Dense real publications should still drive the public
        # 24-hour view, including the in-progress current-hour candle.
        closed_hours = [
            hour_start for hour_start in sorted(ticks_by_hour)
            if hour_start + timedelta(hours=1) <= now
        ][-24:]
        for index, hour_start in enumerate(closed_hours):
            values = ticks_by_hour[hour_start]
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=hour_start,
                end_time=hour_start + timedelta(hours=1), open_price_cny=values[0],
                high_price_cny=max(values), low_price_cny=min(values),
                close_price_cny=values[-1], sample_count=len(values) * 4,
                observation_count=len(values), method="official_hourly",
                data_quality="official_full", source_version="hourly-v1",
                signature=f"matching-official-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(payload["tick_seconds"], 5 * 60)
        self.assertEqual(payload["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(payload["provenance"]["kind"], "direct_observation")
        self.assertEqual(len(payload["candles"]), 24)
        self.assertEqual(payload["candles"][0]["start_time"], "2026-08-17T09:00:00Z")
        current = payload["candles"][-1]
        self.assertEqual(current["start_time"], "2026-08-18T08:00:00Z")
        self.assertEqual(current["end_time"], "2026-08-18T09:00:00Z")
        self.assertEqual(current["observation_count"], 6)
        self.assertEqual(current["open_price_cny"], 30.283)
        self.assertEqual(current["high_price_cny"], 30.288)
        self.assertEqual(current["low_price_cny"], 30.283)
        self.assertEqual(current["close_price_cny"], 30.288)
        self.assertEqual(payload["history_coverage_status"], "complete")
        self.assertTrue(payload["latest_live_comparable_to_history"])
        db.close()

    def test_dense_snapshots_consistent_with_selected_four_hour_history_ignore_bad_native_hourly_series(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 25)
        official_start = datetime(2026, 8, 17, 8, 0)

        # Native 1h is a materially different official publication. The stored
        # selector must reject it in favour of the matching native 4h series.
        for index in range(24):
            candle_start = official_start + timedelta(hours=index)
            value = Decimal("29") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=8, observation_count=8, method="official_hourly",
                data_quality="official_full", source_version="hourly-bad-v1",
                signature=f"bad-native-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        for index in range(6):
            candle_start = official_start + timedelta(hours=index * 4)
            value = Decimal("27") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=32, observation_count=32, method="official_four_hour",
                data_quality="official_full", source_version="four-hour-good-v1",
                signature=f"selected-four-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        # The complete five-minute publication stream follows the selected 4h
        # level exactly. It should therefore be exposed as 24 real 1h candles;
        # the rejected 1h official series must not veto this consistent stream.
        first_observation = now - timedelta(hours=24)
        for index in range(24 * 12 + 1):
            observed = first_observation + timedelta(minutes=index * 5)
            block = int((observed - official_start).total_seconds() // (4 * 60 * 60))
            value = Decimal("27") + Decimal(block) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"four-hour-consistent-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(payload["tick_seconds"], 5 * 60)
        self.assertEqual(payload["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(payload["provenance"]["kind"], "direct_observation")
        self.assertEqual(len(payload["candles"]), 24)
        self.assertTrue(all(candle["high_price_cny"] < 28 for candle in payload["candles"]))
        self.assertEqual(payload["candles"][-1]["start_time"], "2026-08-18T08:00:00Z")
        self.assertEqual(payload["candles"][-1]["observation_count"], 6)
        self.assertTrue(payload["latest_live_comparable_to_history"])
        db.close()

    def test_new_five_minute_publication_updates_current_hour_without_adding_a_candle(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        first_now = datetime(2026, 8, 18, 8, 20)
        first_observation = first_now - timedelta(hours=24)
        for index in range(24 * 12 + 1):
            observed = first_observation + timedelta(minutes=index * 5)
            value = Decimal("40") + Decimal(index) / Decimal("1000")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"current-hour-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=first_now):
            before = _price_candles_payload(
                "RTX4090", "24GB", "24h", "kai", "ondemand", db,
            )

        next_observation = first_now + timedelta(minutes=5)
        next_value = Decimal("40.289")
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
            currency="CNY", min_price=next_value, p25_price=next_value,
            median_price=next_value, p75_price=next_value, max_price=next_value,
            min_price_cny=next_value, median_price_cny=next_value,
            max_price_cny=next_value, sample_count=4, available_gpu_count=4,
            fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="current-hour-snapshot-next",
            observed_at=next_observation, fetched_at=next_observation,
        ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=next_observation):
            after = _price_candles_payload(
                "RTX4090", "24GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(len(before["candles"]), 24)
        self.assertEqual(len(after["candles"]), 24)
        before_current = before["candles"][-1]
        after_current = after["candles"][-1]
        self.assertEqual(before_current["start_time"], after_current["start_time"])
        self.assertEqual(before_current["end_time"], after_current["end_time"])
        self.assertEqual(after_current["start_time"], "2026-08-18T08:00:00Z")
        self.assertEqual(before_current["observation_count"], 5)
        self.assertEqual(after_current["observation_count"], 6)
        self.assertEqual(before_current["open_price_cny"], after_current["open_price_cny"])
        self.assertEqual(before_current["close_price_cny"], 40.288)
        self.assertEqual(after_current["close_price_cny"], 40.289)
        self.assertEqual(after_current["high_price_cny"], 40.289)
        db.close()

    def test_twenty_four_hour_sparse_snapshots_fall_back_to_official_history_without_splicing(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        start = now - timedelta(hours=24)
        for index in range(24):
            candle_start = start + timedelta(hours=index)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value + Decimal("0.01"), low_price_cny=value - Decimal("0.01"),
                close_price_cny=value, sample_count=8, observation_count=8,
                method="official_hourly", data_quality="official_full",
                source_version="hourly-v1", signature=f"sparse-fallback-hour-{index}",
                source_observed_at=now, collected_at=now, updated_at=now,
            ))
        for index in range(6):
            observed = now - timedelta(minutes=25 - index * 5)
            value = Decimal("50") + Decimal(index) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"sparse-live-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "official_hourly")
        self.assertEqual(payload["provenance"]["kind"], "stored_official_historical_ohlc")
        self.assertEqual(len(payload["candles"]), 24)
        self.assertTrue(all(candle["high_price_cny"] < 31 for candle in payload["candles"]))
        self.assertEqual(payload["latest_live_price_cny"], 50.05)
        self.assertFalse(payload["latest_live_comparable_to_history"])
        self.assertFalse(payload["provenance"]["live_component_included"])
        self.assertEqual(payload["candles"][-1]["end_time"], "2026-08-18T08:00:00Z")
        db.close()

    def test_twenty_four_hour_complete_official_window_wins_while_snapshot_index_is_building(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 10, 0)
        official_start = datetime(2026, 8, 17, 10, 0)
        for index in range(24):
            candle_start = official_start + timedelta(hours=index)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value + Decimal("0.01"), low_price_cny=value - Decimal("0.01"),
                close_price_cny=value, sample_count=8, observation_count=8,
                method="official_hourly", data_quality="official_full",
                source_version="hourly-v1", signature=f"building-fallback-hour-{index}",
                source_observed_at=now, collected_at=now, updated_at=now,
            ))
        for hour_index in range(8):
            hour_start = datetime(2026, 8, 18, 2, 0) + timedelta(hours=hour_index)
            for tick_index in range(12):
                observed = hour_start + timedelta(minutes=tick_index * 5)
                value = Decimal("50") + Decimal(hour_index) / Decimal("100")
                db.add(MarketPriceSnapshot(
                    source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                    currency="CNY", min_price=value, p25_price=value, median_price=value,
                    p75_price=value, max_price=value, min_price_cny=value,
                    median_price_cny=value, max_price_cny=value, sample_count=4,
                    available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                    fx_date="2026-08-18", data_quality="verified",
                    signature=f"building-live-{hour_index}-{tick_index}", observed_at=observed,
                    fetched_at=observed,
                ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "official_hourly")
        self.assertEqual(payload["provenance"]["kind"], "stored_official_historical_ohlc")
        self.assertEqual(payload["snapshot_candidate_status"], "building")
        self.assertEqual(payload["snapshot_candidate_candle_count"], 8)
        self.assertEqual(len(payload["candles"]), 24)
        self.assertTrue(all(candle["high_price_cny"] < 31 for candle in payload["candles"]))
        self.assertFalse(payload["latest_live_comparable_to_history"])
        db.close()

    def test_recent_partial_hourly_snapshots_are_shown_while_five_minute_window_builds(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 10, 10)

        # A complete but coarser official fallback exists. The local collector
        # has accumulated nine consecutive one-hour buckets from real five-
        # minute publications. Its oldest startup hour is too sparse, while the
        # newest eight hours each retain at least half of their expected ticks.
        official_start = datetime(2026, 8, 17, 8, 0)
        for index in range(6):
            candle_start = official_start + timedelta(hours=index * 4)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=32, observation_count=32, method="official_four_hour",
                data_quality="official_full", source_version="four-hour-v1",
                signature=f"partial-building-official-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        hourly_tick_counts = [2, 11, 12, 12, 10, 7, 9, 10, 3]
        first_hour = datetime(2026, 8, 18, 2, 0)
        for hour_index, tick_count in enumerate(hourly_tick_counts):
            hour_start = first_hour + timedelta(hours=hour_index)
            for tick_index in range(tick_count):
                observed = hour_start + timedelta(minutes=tick_index * 5)
                value = Decimal("50") + Decimal(hour_index) / Decimal("10") + Decimal(tick_index) / Decimal("1000")
                db.add(MarketPriceSnapshot(
                    source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
                    currency="CNY", min_price=value, p25_price=value, median_price=value,
                    p75_price=value, max_price=value, min_price_cny=value,
                    median_price_cny=value, max_price_cny=value, sample_count=4,
                    available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                    fx_date="2026-08-18", data_quality="verified",
                    signature=f"partial-building-{hour_index}-{tick_index}",
                    observed_at=observed, fetched_at=observed,
                ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "94GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(payload["tick_seconds"], 5 * 60)
        self.assertEqual(payload["snapshot_candidate_status"], "building")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["expected_bucket_count"], 24)
        self.assertEqual(len(payload["candles"]), 8)
        self.assertEqual(payload["candles"][0]["start_time"], "2026-08-18T03:00:00Z")
        self.assertEqual(payload["candles"][-1]["start_time"], "2026-08-18T10:00:00Z")
        self.assertGreaterEqual(payload["minimum_hour_tick_coverage_ratio"], 0.5)
        self.assertEqual(payload["provenance"]["kind"], "direct_observation")
        self.assertTrue(payload["latest_live_comparable_to_history"])
        db.close()

    def test_twenty_four_hour_dense_offer_pool_index_is_selected_even_when_official_index_differs(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 25)
        start = now - timedelta(hours=24)
        for index in range(24 * 12 + 1):
            observed = start + timedelta(minutes=index * 5)
            value = Decimal("50") + Decimal(index) / Decimal("10000")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"inconsistent-dense-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))
        official_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=24)
        for index in range(24):
            candle_start = official_start + timedelta(hours=index)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value + Decimal("0.01"), low_price_cny=value - Decimal("0.01"),
                close_price_cny=value, sample_count=8, observation_count=8,
                method="official_hourly", data_quality="official_full",
                source_version="hourly-v1", signature=f"inconsistent-official-hour-{index}",
                source_observed_at=now, collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(payload["provenance"]["kind"], "direct_observation")
        self.assertEqual(len(payload["candles"]), 24)
        self.assertEqual(payload["tick_seconds"], 5 * 60)
        self.assertTrue(all(candle["low_price_cny"] > 49 for candle in payload["candles"]))
        self.assertGreater(payload["latest_live_price_cny"], 50)
        self.assertTrue(payload["latest_live_comparable_to_history"])
        self.assertTrue(payload["provenance"]["live_component_included"])
        self.assertEqual(payload["snapshot_candidate_status"], "ready")
        self.assertEqual(payload["observed_tick_coverage_ratio"], 1.0)
        self.assertEqual(payload["minimum_hour_tick_coverage_ratio"], 1.0)
        self.assertEqual(payload["candles"][-1]["end_time"], "2026-08-18T09:00:00Z")
        db.close()

    def test_duplicate_snapshot_rows_in_one_five_minute_slot_do_not_inflate_tick_coverage(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        official_start = now - timedelta(hours=24)
        for index in range(24):
            candle_start = official_start + timedelta(hours=index)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=8, observation_count=8, method="official_hourly",
                data_quality="official_full", source_version="hourly-v1",
                signature=f"duplicate-slot-official-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        # Twenty-four hourly buckets exist, but each has only one distinct
        # five-minute publication slot. Twelve duplicate DB rows in that slot
        # must remain one tick rather than pretending to be twelve ticks.
        first_hour = now - timedelta(hours=23)
        for hour_index in range(24):
            observed = first_hour + timedelta(hours=hour_index)
            for duplicate_index in range(12):
                value = Decimal("50") + Decimal(hour_index) / Decimal("100")
                db.add(MarketPriceSnapshot(
                    source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                    currency="CNY", min_price=value, p25_price=value, median_price=value,
                    p75_price=value, max_price=value, min_price_cny=value,
                    median_price_cny=value, max_price_cny=value, sample_count=1,
                    available_gpu_count=1, fx_rate=Decimal("1"), fx_source="test",
                    fx_date="2026-08-18", data_quality="verified",
                    signature=f"duplicate-slot-{hour_index}-{duplicate_index}",
                    observed_at=observed, fetched_at=observed,
                ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "official_hourly")
        self.assertEqual(payload["provenance"]["kind"], "stored_official_historical_ohlc")
        self.assertEqual(payload["snapshot_candidate_status"], "insufficient_five_minute_coverage")
        self.assertEqual(payload["snapshot_candidate_candle_count"], 24)
        self.assertEqual(payload["snapshot_candidate_expected_candle_count"], 24)
        self.assertEqual(payload["snapshot_candidate_tick_coverage_ratio"], 0.0833)
        self.assertEqual(payload["snapshot_candidate_minimum_hour_coverage_ratio"], 0.0833)
        self.assertTrue(all(candle["high_price_cny"] < 31 for candle in payload["candles"]))
        db.close()

    def test_one_undercovered_closed_hour_forces_official_fallback_despite_high_global_tick_coverage(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 25)
        official_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=24)
        for index in range(24):
            candle_start = official_start + timedelta(hours=index)
            value = Decimal("30") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=8, observation_count=8, method="official_hourly",
                data_quality="official_full", source_version="hourly-v1",
                signature=f"undercovered-hour-official-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        first_observation = now - timedelta(hours=24)
        undercovered_hour = datetime(2026, 8, 17, 14, 0)
        for index in range(24 * 12 + 1):
            observed = first_observation + timedelta(minutes=index * 5)
            if (
                observed.replace(minute=0, second=0, microsecond=0) == undercovered_hour
                and observed.minute in {20, 40}
            ):
                continue
            value = Decimal("50") + Decimal(index) / Decimal("10000")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value,
                median_price_cny=value, max_price_cny=value, sample_count=4,
                available_gpu_count=4, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="verified",
                signature=f"undercovered-hour-snapshot-{index}", observed_at=observed,
                fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["method"], "official_hourly")
        self.assertEqual(payload["provenance"]["kind"], "stored_official_historical_ohlc")
        self.assertEqual(payload["snapshot_candidate_status"], "insufficient_five_minute_coverage")
        self.assertEqual(payload["snapshot_candidate_candle_count"], 24)
        self.assertGreaterEqual(payload["snapshot_candidate_tick_coverage_ratio"], 0.85)
        self.assertEqual(payload["snapshot_candidate_minimum_hour_coverage_ratio"], 0.8333)
        self.assertTrue(all(candle["high_price_cny"] < 31 for candle in payload["candles"]))
        db.close()

    def test_thirty_day_snapshot_window_with_only_seven_days_remains_partial(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for day in range(8):
            observed = now - timedelta(days=7 - day)
            value = Decimal("5") + Decimal(day) / Decimal("100")
            db.add(MarketPriceSnapshot(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=4, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=f"snapshot-30d-{day}", observed_at=observed, fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "RTX4090", "24GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["history_status"], "partial_history")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["coverage_day_count"], 8)
        self.assertAlmostEqual(payload["coverage_span_hours"], 168.0)
        db.close()

    def test_stored_history_selects_the_exact_resolution_for_each_range(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("9"), p25_price=Decimal("9"), median_price=Decimal("9"),
            p75_price=Decimal("9"), max_price=Decimal("9"), min_price_cny=Decimal("9"),
            median_price_cny=Decimal("9"), max_price_cny=Decimal("9"), sample_count=4,
            available_gpu_count=0, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="latest-resolution", observed_at=now, fetched_at=now,
        ))
        for index in range(24):
            candle_start = now - timedelta(hours=24 - index)
            # Match the six overlapping native four-hour candles exactly so
            # this case verifies that a consistent native 1h series remains
            # the preferred public resolution.
            value = Decimal("20") + Decimal(174 + index // 4) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=2, observation_count=2, method="official_hourly", data_quality="official",
                source_version="v1", signature=f"stored-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        for index in range(180):
            candle_start = now - timedelta(days=30) + timedelta(hours=index * 4)
            value = Decimal("20") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=2, observation_count=2, method="official_four_hour", data_quality="official",
                source_version="v1", signature=f"stored-four-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            hourly = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )
            four_hour = _price_candles_payload(
                "H100", "80GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(hourly["bucket_seconds"], 60 * 60)
        self.assertEqual(hourly["method"], "official_hourly")
        self.assertEqual(len(hourly["candles"]), 24)
        self.assertGreater(min(item["low_price_cny"] for item in hourly["candles"]), 19)
        self.assertEqual(hourly["resolution_consistency_status"], "not_evaluated")
        self.assertEqual(four_hour["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(four_hour["method"], "official_four_hour")
        self.assertEqual(len(four_hour["candles"]), 180)
        self.assertGreater(min(item["low_price_cny"] for item in four_hour["candles"]), 19)
        self.assertEqual(four_hour["resolution_consistency_status"], "consistent")
        self.assertEqual(four_hour["resolution_consistency"]["compared_bucket_count"], 6)
        self.assertEqual(
            four_hour["resolution_consistency"]["median_close_deviation_ratio"], 0,
        )
        self.assertEqual(four_hour["resolution_status"], "requested")
        self.assertIsNone(four_hour["resolution_fallback_reason"])
        self.assertEqual(four_hour["history_coverage_status"], "complete")
        db.close()

    def test_thirty_day_resolution_gate_replaces_l40s_style_native_mismatch_with_real_hourly_suffix(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="L40S", gpu_variant="48GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("28"), p25_price=Decimal("28"),
            median_price=Decimal("28"), p75_price=Decimal("28"), max_price=Decimal("28"),
            min_price_cny=Decimal("28"), median_price_cny=Decimal("28"),
            max_price_cny=Decimal("28"), sample_count=4, available_gpu_count=0,
            fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="l40s-live", observed_at=now, fetched_at=now,
        ))

        native_start = now - timedelta(days=30)
        for index in range(180):
            candle_start = native_start + timedelta(hours=index * 4)
            value = Decimal("42") + Decimal(index) / Decimal("10000")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="L40S", gpu_variant="48GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value + Decimal("0.04"), low_price_cny=value - Decimal("0.04"),
                close_price_cny=value + Decimal("0.01"), sample_count=1, observation_count=1,
                method="official_four_hour", data_quality="official", source_version="same-v1",
                signature=f"l40s-native-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        hourly_start = now - timedelta(days=7)
        for index in range(168):
            candle_start = hourly_start + timedelta(hours=index)
            group = index // 4
            value = Decimal("25") + Decimal(group) / Decimal("10000")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="L40S", gpu_variant="48GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value + Decimal("0.03"), low_price_cny=value - Decimal("0.02"),
                close_price_cny=value + Decimal("0.01"), sample_count=4, observation_count=4,
                method="official_hourly", data_quality="official", source_version="same-v1",
                signature=f"l40s-hourly-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "L40S", "48GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["requested_bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(payload["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(payload["expected_bucket_count"], 180)
        self.assertEqual(len(payload["candles"]), 42)
        self.assertEqual(payload["candles"][0]["start_time"], "2026-08-11T08:00:00Z")
        self.assertEqual(payload["candles"][-1]["end_time"], "2026-08-18T08:00:00Z")
        self.assertTrue(all(item["high_price_cny"] < 30 for item in payload["candles"]))
        self.assertTrue(all(item["sample_count"] == 4 for item in payload["candles"]))
        self.assertTrue(all(item["observation_count"] == 16 for item in payload["candles"]))
        self.assertEqual(payload["method"], "official_hourly_aggregated_four_hour")
        self.assertFalse(payload["is_interpolated"])
        self.assertEqual(payload["resolution_status"], "fallback_aggregated_from_hourly")
        self.assertEqual(
            payload["resolution_fallback_reason"],
            "native_four_hour_inconsistent_with_hourly_overlap",
        )
        self.assertEqual(payload["partial_reason"], payload["resolution_fallback_reason"])
        self.assertEqual(payload["resolution_consistency_status"], "inconsistent")
        self.assertGreater(
            payload["resolution_consistency"]["median_close_deviation_ratio"], 0.3,
        )
        self.assertEqual(payload["aggregation_source_bucket_seconds"], 60 * 60)
        self.assertEqual(payload["history_status"], "partial_history")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["coverage_span_hours"], 7 * 24)
        self.assertEqual(
            payload["provenance"]["kind"], "stored_official_hourly_aggregated_ohlc",
        )
        self.assertTrue(payload["provenance"]["native_four_hour_quarantined"])
        db.close()

    def test_thirty_day_resolution_gate_keeps_native_when_hourly_overlap_is_insufficient(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        native_start = now - timedelta(days=30)
        for index in range(180):
            candle_start = native_start + timedelta(hours=index * 4)
            value = Decimal("30") + Decimal(index) / Decimal("10000")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value + Decimal("0.02"), low_price_cny=value - Decimal("0.02"),
                close_price_cny=value, sample_count=8, observation_count=8,
                method="official_four_hour", data_quality="official", source_version="native-v1",
                signature=f"insufficient-native-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))

        # Three comparable four-hour windows are below the minimum gate size.
        hourly_start = now - timedelta(hours=12)
        for index in range(12):
            candle_start = hourly_start + timedelta(hours=index)
            value = Decimal("50") + Decimal(index // 4) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=8, observation_count=8, method="official_hourly",
                data_quality="official", source_version="hourly-v1",
                signature=f"insufficient-hourly-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["resolution_consistency_status"], "insufficient_overlap")
        self.assertEqual(payload["resolution_consistency"]["compared_bucket_count"], 3)
        self.assertEqual(payload["resolution_status"], "requested")
        self.assertIsNone(payload["resolution_fallback_reason"])
        self.assertEqual(payload["method"], "official_four_hour")
        self.assertEqual(len(payload["candles"]), 180)
        self.assertEqual(payload["history_coverage_status"], "complete")
        self.assertTrue(all(item["high_price_cny"] < 31 for item in payload["candles"]))
        db.close()

    def test_inconsistent_cross_resolution_history_keeps_the_public_hourly_contract(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("25"), p25_price=Decimal("25"),
            median_price=Decimal("25"), p75_price=Decimal("25"), max_price=Decimal("25"),
            min_price_cny=Decimal("25"), median_price_cny=Decimal("25"),
            max_price_cny=Decimal("25"), sample_count=8, available_gpu_count=0,
            fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="inconsistent-live", observed_at=now, fetched_at=now,
        ))
        start = now - timedelta(hours=24)
        for index in range(24):
            candle_start = start + timedelta(hours=index)
            value = Decimal("29") + Decimal(index // 4) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=4, observation_count=4, method="official_hourly",
                data_quality="official", source_version="hourly-v1",
                signature=f"inconsistent-hourly-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        for index in range(6):
            candle_start = start + timedelta(hours=index * 4)
            value = Decimal("27") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=4, observation_count=4, method="official_four_hour",
                data_quality="official", source_version="four-hour-v1",
                signature=f"inconsistent-four-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["requested_bucket_seconds"], 60 * 60)
        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(len(payload["candles"]), 24)
        self.assertEqual(payload["resolution_status"], "requested")
        self.assertIsNone(payload["resolution_fallback_reason"])
        self.assertEqual(payload["resolution_consistency_status"], "not_evaluated")
        self.assertIsNone(payload["resolution_consistency"])
        self.assertEqual(payload["curve_status"], "full")
        self.assertEqual(payload["history_status"], "available")
        self.assertEqual(payload["history_coverage_status"], "complete")
        self.assertTrue(all(item["close_price_cny"] >= 29 for item in payload["candles"]))
        db.close()

    def test_resolution_gate_ignores_one_isolated_four_hour_outlier(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("27"), p25_price=Decimal("27"),
            median_price=Decimal("27"), p75_price=Decimal("27"), max_price=Decimal("27"),
            min_price_cny=Decimal("27"), median_price_cny=Decimal("27"),
            max_price_cny=Decimal("27"), sample_count=8, available_gpu_count=0,
            fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="outlier-live", observed_at=now, fetched_at=now,
        ))
        start = now - timedelta(hours=24)
        for index in range(24):
            candle_start = start + timedelta(hours=index)
            value = Decimal("27") + Decimal(index // 4) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=4, observation_count=4, method="official_hourly",
                data_quality="official", source_version="hourly-v1",
                signature=f"outlier-hourly-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        for index in range(6):
            candle_start = start + timedelta(hours=index * 4)
            value = Decimal("20") if index == 0 else Decimal("27") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=4), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=4, observation_count=4, method="official_four_hour",
                data_quality="official", source_version="four-hour-v1",
                signature=f"outlier-four-hour-{index}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "24h", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 60 * 60)
        self.assertEqual(payload["resolution_status"], "requested")
        self.assertEqual(payload["resolution_consistency_status"], "not_evaluated")
        self.assertIsNone(payload["resolution_consistency"])
        self.assertEqual(len(payload["candles"]), 24)
        db.close()

    def test_thirty_day_history_quarantines_superseded_partial_tail_and_refills_from_overfetch(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        interval = timedelta(hours=4)
        trusted_observed_at = now - timedelta(minutes=5)

        # One extra trusted bucket is deliberately outside the public 180-candle
        # window. It may refill the oldest edge only after the stale newest
        # bucket is quarantined, preserving a real contiguous 30-day series.
        for index in range(180):
            candle_start = now - interval * (181 - index)
            value = Decimal("84") + Decimal(index) / Decimal("1000")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + interval, open_price_cny=value,
                high_price_cny=value + Decimal("0.04"), low_price_cny=value - Decimal("0.04"),
                close_price_cny=value, sample_count=4, observation_count=4,
                method="official_four_hour", data_quality="official_full",
                source_version="official-v2", signature=f"trusted-30d-{index}",
                source_observed_at=trusted_observed_at,
                collected_at=trusted_observed_at, updated_at=trusted_observed_at,
            ))

        bad_start = now - interval
        db.add(MarketPriceCandle(
            source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
            interval_seconds=4 * 60 * 60, start_time=bad_start, end_time=now,
            open_price_cny=Decimal("73"), high_price_cny=Decimal("73.1"),
            low_price_cny=Decimal("72.9"), close_price_cny=Decimal("73"),
            sample_count=1, observation_count=1, method="official_four_hour",
            data_quality="official_partial", source_version="official-v1-partial",
            signature="superseded-partial-tail", source_observed_at=now - timedelta(days=1),
            collected_at=now - timedelta(days=1), updated_at=now - timedelta(days=1),
        ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "94GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(len(payload["candles"]), 180)
        self.assertEqual(payload["expected_bucket_count"], 180)
        self.assertEqual(payload["curve_status"], "full")
        self.assertEqual(payload["history_coverage_status"], "complete")
        self.assertEqual(payload["coverage_span_hours"], 30 * 24)
        self.assertEqual(payload["quarantined_candle_count"], 1)
        self.assertEqual(payload["quarantined_prefix_count"], 0)
        self.assertEqual(payload["quarantined_tail_count"], 1)
        self.assertEqual(payload["quarantine_reason"], "superseded_partial_edge_batch")
        self.assertEqual(payload["provenance"]["quarantined_candle_count"], 1)
        self.assertEqual(payload["provenance"]["quarantined_tail_count"], 1)
        self.assertEqual(payload["provenance"]["source_version"], "official-v2")
        self.assertEqual(payload["provenance"]["history_as_of"], "2026-08-18T04:00:00Z")
        self.assertTrue(all(candle["low_price_cny"] > 80 for candle in payload["candles"]))
        self.assertEqual(payload["candles"][0]["start_time"], "2026-07-19T04:00:00Z")
        self.assertEqual(payload["candles"][-1]["end_time"], "2026-08-18T04:00:00Z")
        db.close()

    def test_thirty_day_history_quarantines_superseded_partial_prefix_without_bridging_gap(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        interval = timedelta(hours=4)
        trusted_observed_at = now - timedelta(minutes=5)

        # The oldest trusted row is overfetch only. Refilling it after removing
        # the first public bucket would bridge the removed bucket's timestamp,
        # so the API must leave the result partial instead of inventing coverage.
        overfetch_start = now - interval * 181
        db.add(MarketPriceCandle(
            source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
            interval_seconds=4 * 60 * 60, start_time=overfetch_start,
            end_time=overfetch_start + interval, open_price_cny=Decimal("73"),
            high_price_cny=Decimal("73.05"), low_price_cny=Decimal("72.95"),
            close_price_cny=Decimal("73"), sample_count=4, observation_count=4,
            method="official_four_hour", data_quality="official_full",
            source_version="official-v2", signature="trusted-7d-overfetch",
            source_observed_at=trusted_observed_at,
            collected_at=trusted_observed_at, updated_at=trusted_observed_at,
        ))
        bad_start = now - interval * 180
        db.add(MarketPriceCandle(
            source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
            interval_seconds=4 * 60 * 60, start_time=bad_start,
            end_time=bad_start + interval, open_price_cny=Decimal("62"),
            high_price_cny=Decimal("62.1"), low_price_cny=Decimal("61.9"),
            close_price_cny=Decimal("62"), sample_count=1, observation_count=1,
            method="official_four_hour", data_quality="official_partial",
            source_version="official-v1-partial", signature="superseded-partial-prefix",
            source_observed_at=now - timedelta(days=1),
            collected_at=now - timedelta(days=1), updated_at=now - timedelta(days=1),
        ))
        for index in range(179):
            candle_start = now - interval * (179 - index)
            value = Decimal("73") + Decimal(index) / Decimal("1000")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + interval, open_price_cny=value,
                high_price_cny=value + Decimal("0.04"), low_price_cny=value - Decimal("0.04"),
                close_price_cny=value, sample_count=4, observation_count=4,
                method="official_four_hour", data_quality="official_full",
                source_version="official-v2", signature=f"trusted-7d-{index}",
                source_observed_at=trusted_observed_at,
                collected_at=trusted_observed_at, updated_at=trusted_observed_at,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "94GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(len(payload["candles"]), 179)
        self.assertEqual(payload["expected_bucket_count"], 180)
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["history_status"], "partial_history")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["coverage_span_hours"], 179 * 4)
        self.assertAlmostEqual(payload["observed_bucket_coverage_ratio"], 179 / 180, places=4)
        self.assertEqual(payload["quarantined_candle_count"], 1)
        self.assertEqual(payload["quarantined_prefix_count"], 1)
        self.assertEqual(payload["quarantined_tail_count"], 0)
        self.assertEqual(payload["provenance"]["temporal_coverage_status"], "partial")
        self.assertEqual(
            payload["candles"][0]["start_time"],
            (now - interval * 179).isoformat(timespec="seconds") + "Z",
        )
        self.assertGreater(payload["candles"][0]["low_price_cny"], 70)
        self.assertNotIn(bad_start.isoformat(timespec="seconds") + "Z", {
            candle["start_time"] for candle in payload["candles"]
        })
        db.close()

    def test_full_current_three_candle_repricing_is_not_quarantined(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        interval = timedelta(hours=4)
        start = now - timedelta(hours=24)

        for index in range(6):
            candle_start = start + interval * index
            value = Decimal("84") if index < 3 else Decimal("73")
            observed_at = now - timedelta(minutes=6 - index)
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="94GB", billing_mode="ondemand",
                interval_seconds=4 * 60 * 60, start_time=candle_start,
                end_time=candle_start + interval, open_price_cny=value,
                high_price_cny=value + Decimal("0.05"), low_price_cny=value - Decimal("0.05"),
                close_price_cny=value, sample_count=8, observation_count=8,
                method="official_four_hour", data_quality="official_full",
                source_version="official-v3", signature=f"confirmed-repricing-{index}",
                source_observed_at=observed_at, collected_at=observed_at, updated_at=observed_at,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "94GB", "30d", "kai", "ondemand", db,
            )

        self.assertEqual(payload["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(len(payload["candles"]), 6)
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["quarantined_candle_count"], 0)
        self.assertEqual(payload["quarantined_prefix_count"], 0)
        self.assertEqual(payload["quarantined_tail_count"], 0)
        self.assertIsNone(payload["quarantine_reason"])
        self.assertEqual(
            [candle["close_price_cny"] for candle in payload["candles"]],
            [84.0, 84.0, 84.0, 73.0, 73.0, 73.0],
        )
        db.close()

    def test_stored_history_keeps_fixed_resolution_when_primary_is_partial(self):
        cases = (
            ("7d", 60 * 60, 80, 4 * 60 * 60, 42),
            ("30d", 4 * 60 * 60, 90, 24 * 60 * 60, 30),
        )
        now = datetime(2026, 8, 18, 8, 0)
        for range_name, primary_seconds, primary_count, fallback_seconds, fallback_count in cases:
            with self.subTest(range_name=range_name):
                engine = create_engine(
                    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
                )
                MarketPriceSnapshot.__table__.create(engine)
                MarketPriceCandle.__table__.create(engine)
                MarketCandleSyncStatus.__table__.create(engine)
                db = sessionmaker(bind=engine)()
                db.add(MarketPriceSnapshot(
                    source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                    currency="CNY", min_price=Decimal("25"), p25_price=Decimal("25"),
                    median_price=Decimal("25"), p75_price=Decimal("25"), max_price=Decimal("25"),
                    min_price_cny=Decimal("25"), median_price_cny=Decimal("25"),
                    max_price_cny=Decimal("25"), sample_count=8, available_gpu_count=0,
                    fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
                    data_quality="verified", signature=f"fallback-live-{range_name}",
                    observed_at=now, fetched_at=now,
                ))
                for label, interval_seconds, count, base in (
                    ("primary", primary_seconds, primary_count, Decimal("5")),
                    ("fallback", fallback_seconds, fallback_count, Decimal("20")),
                ):
                    step = timedelta(seconds=interval_seconds)
                    for index in range(count):
                        candle_start = now - step * (count - index)
                        value = base + Decimal(index) / Decimal("100")
                        db.add(MarketPriceCandle(
                            source="kai", gpu_model="H100", gpu_variant="80GB",
                            billing_mode="ondemand", interval_seconds=interval_seconds,
                            start_time=candle_start, end_time=candle_start + step,
                            open_price_cny=value, high_price_cny=value,
                            low_price_cny=value, close_price_cny=value,
                            sample_count=2, observation_count=2, method=f"official_{label}",
                            data_quality="official", source_version="v1",
                            signature=f"fallback-{range_name}-{label}-{index}",
                            source_observed_at=now, collected_at=now, updated_at=now,
                        ))
                db.commit()

                with patch("app.routers.market.utcnow", return_value=now):
                    payload = _price_candles_payload(
                        "H100", "80GB", range_name, "kai", "ondemand", db,
                    )

                self.assertEqual(payload["bucket_seconds"], primary_seconds)
                self.assertEqual(len(payload["candles"]), primary_count)
                self.assertEqual(payload["resolution_status"], "requested")
                self.assertEqual(payload["curve_status"], "partial")
                self.assertEqual(payload["history_status"], "partial_history")
                self.assertEqual(payload["history_coverage_status"], "partial")
                self.assertEqual(payload["provenance"]["temporal_coverage_status"], "partial")
                self.assertGreaterEqual(min(item["low_price_cny"] for item in payload["candles"]), 5)
                db.close()

    def test_stale_complete_stored_window_is_never_reported_full(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        history_end = now - timedelta(days=3)
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
            currency="CNY", min_price=Decimal("25"), p25_price=Decimal("25"),
            median_price=Decimal("25"), p75_price=Decimal("25"), max_price=Decimal("25"),
            min_price_cny=Decimal("25"), median_price_cny=Decimal("25"),
            max_price_cny=Decimal("25"), sample_count=8, available_gpu_count=0,
            fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="stale-live", observed_at=now, fetched_at=now,
        ))
        for index in range(168):
            candle_start = history_end - timedelta(hours=168 - index)
            value = Decimal("20") + Decimal(index) / Decimal("100")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="H100", gpu_variant="80GB", billing_mode="ondemand",
                interval_seconds=60 * 60, start_time=candle_start,
                end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                high_price_cny=value, low_price_cny=value, close_price_cny=value,
                sample_count=2, observation_count=2, method="official_hourly",
                data_quality="official", source_version="v1", signature=f"stale-{index}",
                source_observed_at=history_end, collected_at=history_end, updated_at=history_end,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            payload = _price_candles_payload(
                "H100", "80GB", "7d", "kai", "ondemand", db,
            )

        self.assertEqual(len(payload["candles"]), 168)
        self.assertEqual(payload["history_status"], "partial_history")
        self.assertEqual(payload["curve_status"], "partial")
        self.assertEqual(payload["history_coverage_status"], "partial")
        self.assertEqual(payload["provenance"]["temporal_coverage_status"], "complete")
        self.assertEqual(payload["provenance"]["history_freshness_status"], "stale")
        db.close()

    def test_six_hour_curve_prefers_complete_snapshots_and_falls_back_as_one_official_series(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        MarketPriceCandle.__table__.create(engine)
        MarketCandleSyncStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)

        def snapshot(model: str, variant: str, observed: datetime, value: Decimal, signature: str):
            return MarketPriceSnapshot(
                source="kai", gpu_model=model, gpu_variant=variant, billing_mode="ondemand",
                currency="CNY", min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value, min_price_cny=value, median_price_cny=value,
                max_price_cny=value, sample_count=4, available_gpu_count=0, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-18", data_quality="verified",
                signature=signature, observed_at=observed, fetched_at=observed,
            )

        # RTX4090 has a complete five-minute publication history, which must
        # remain the preferred 15-minute snapshot-derived curve.
        for index in range(73):
            observed = now - timedelta(hours=6) + timedelta(minutes=index * 5)
            db.add(snapshot(
                "RTX4090", "24GB", observed,
                Decimal("5") + Decimal(index) / Decimal("1000"),
                f"dense-6h-{index}",
            ))
        # H100 spans six hours but has only three isolated observations. Even
        # the one-hour snapshot candidate is sparse, so it must fall back.
        for index, hours in enumerate((6, 3, 0)):
            observed = now - timedelta(hours=hours)
            db.add(snapshot(
                "H100", "80GB", observed,
                Decimal("9") + Decimal(index) / Decimal("100"),
                f"sparse-6h-{index}",
            ))
        for model, variant, base in (
            ("RTX4090", "24GB", Decimal("90")),
            ("H100", "80GB", Decimal("20")),
        ):
            for index in range(6):
                candle_start = now - timedelta(hours=6 - index)
                value = base + Decimal(index) / Decimal("100")
                db.add(MarketPriceCandle(
                    source="kai", gpu_model=model, gpu_variant=variant, billing_mode="ondemand",
                    interval_seconds=60 * 60, start_time=candle_start,
                    end_time=candle_start + timedelta(hours=1), open_price_cny=value,
                    high_price_cny=value, low_price_cny=value, close_price_cny=value,
                    sample_count=2, observation_count=2, method="official_hourly",
                    data_quality="official", source_version="v1",
                    signature=f"official-6h-{model}-{index}", source_observed_at=now,
                    collected_at=now, updated_at=now,
                ))
        db.add(MarketCandleSyncStatus(
            source="kai", status="ok", refresh_seconds=300, model_count=2,
            candle_count=12, last_attempt_at=now, last_success_at=now,
        ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now):
            dense = _price_candles_payload(
                "RTX4090", "24GB", "6h", "kai", "ondemand", db,
            )
            fallback = _price_candles_payload(
                "H100", "80GB", "6h", "kai", "ondemand", db,
            )

        self.assertEqual(dense["bucket_seconds"], 15 * 60)
        self.assertEqual(dense["method"], "observed_source_robust_median_ohlc")
        self.assertEqual(len(dense["candles"]), 24)
        self.assertLess(max(item["high_price_cny"] for item in dense["candles"]), 10)
        self.assertEqual(fallback["bucket_seconds"], 60 * 60)
        self.assertEqual(fallback["method"], "official_hourly")
        self.assertEqual(len(fallback["candles"]), 6)
        self.assertEqual(fallback["provenance"]["dataset_source"], "market_price_candles")
        self.assertFalse(fallback["provenance"]["live_component_included"])
        self.assertFalse(fallback["latest_live_comparable_to_history"])
        self.assertGreater(min(item["low_price_cny"] for item in fallback["candles"]), 19)
        db.close()

    def test_retired_autodl_cannot_be_selected_for_market_curve(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for index, hours in enumerate((72, 48, 24, 0)):
            value = Decimal("1") + Decimal(index) / Decimal("100")
            observed = now - timedelta(hours=hours)
            db.add(MarketPriceSnapshot(
                source="autodl", gpu_model="RTX5060", gpu_variant="8GB", billing_mode="ondemand", currency="CNY",
                min_price=value, p25_price=value, median_price=value, p75_price=value, max_price=value,
                min_price_cny=value, median_price_cny=value, max_price_cny=value, sample_count=2,
                available_gpu_count=2, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
                data_quality="verified", signature=f"live-{index}", observed_at=observed, fetched_at=observed,
            ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now), self.assertRaises(BizError):
            price_candles("RTX5060", "8GB", "7d", "autodl", "ondemand", db)
        db.close()

    def test_retired_source_single_observation_is_not_exposed(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        value = Decimal("1.25")
        db.add(MarketPriceSnapshot(
            source="autodl", gpu_model="RTX5060TI", gpu_variant="16GB", billing_mode="ondemand", currency="CNY",
            min_price=value, p25_price=value, median_price=value, p75_price=value, max_price=value,
            min_price_cny=value, median_price_cny=value, max_price_cny=value, sample_count=2,
            available_gpu_count=2, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
            data_quality="verified", signature="single", observed_at=now, fetched_at=now,
        ))
        db.commit()

        with patch("app.routers.market.utcnow", return_value=now), self.assertRaises(BizError):
            price_candles("RTX5060TI", "16GB", "7d", "autodl", "ondemand", db)
        db.close()

    def test_h200_140_and_141_labels_resolve_to_one_documented_alias(self):
        self.assertEqual(normalize_gpu_variant("H200", "140GB"), "141GB")
        self.assertEqual(normalize_gpu_variant("H200", "141GB"), "141GB")
        self.assertEqual(normalize_gpu_variant("H100", "94GB"), "94GB")
        self.assertEqual(normalize_gpu_variant("RTX5060TI", "8GB"), "8GB")
        self.assertEqual(gpu_variant_aliases("H200", "140GB"), {"140GB", "141GB"})
        self.assertEqual(gpu_variant_aliases("H100", "94GB"), {"94GB"})

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 8, 0)
        for day in (0, 6):
            value = Decimal("2") + Decimal(day) / Decimal("100")
            db.add(MarketHistoryPoint(
                dataset_source=HF_SOURCE, upstream_provider="runpod", gpu_model="H200", gpu_variant="141GB",
                billing_mode="ondemand", currency="USD", low_price=value, representative_price=value,
                high_price=value, low_price_cny=value, representative_price_cny=value, high_price_cny=value,
                sample_count=2, available_gpu_count=2, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="external_reference", index_method="runpod_reference",
                source_url="https://example.test", license_name="CC BY 4.0", dataset_version="v1",
                signature=f"h200-{day}", observed_at=start + timedelta(days=day), collected_at=start,
            ))
        db.commit()
        selected = select_market_history(db, "H200", "140GB", start, start + timedelta(days=7))
        self.assertIsNotNone(selected)
        self.assertTrue(selected.available)
        self.assertEqual(selected.day_count, 2)
        db.close()

    def test_mixed_retired_market_sources_are_rejected(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime(2026, 8, 18, 8, 0)
        for source, base in (("wod", Decimal("1")), ("autodl", Decimal("10"))):
            for index, hours in enumerate((18, 12, 6, 0)):
                value = base + Decimal(index) / Decimal("100")
                observed = now - timedelta(hours=hours)
                db.add(MarketPriceSnapshot(
                    source=source, gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                    currency="CNY", min_price=value, p25_price=value,
                    median_price=value, p75_price=value, max_price=value, min_price_cny=value,
                    median_price_cny=value, max_price_cny=value, sample_count=2, available_gpu_count=2,
                    fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18", data_quality="verified",
                    signature=f"{source}-{index}", observed_at=observed, fetched_at=observed,
                ))
        db.commit()
        with patch("app.routers.market.utcnow", return_value=now), self.assertRaises(BizError):
            price_candles("RTX4090", "24GB", "24h", "wod,autodl", "ondemand", db)
        db.close()

    def test_sparse_external_series_remains_real_and_chartable_but_limited(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 8, 0)
        for day in range(7):
            value = Decimal("1") + Decimal(day) / Decimal("100")
            db.add(MarketHistoryPoint(
                dataset_source=HF_SOURCE, upstream_provider="vast", gpu_model="RTX3090", gpu_variant="24GB",
                billing_mode="ondemand", currency="USD", low_price=value, representative_price=value,
                high_price=value, low_price_cny=value, representative_price_cny=value, high_price_cny=value,
                sample_count=1, available_gpu_count=1, fx_rate=Decimal("1"), fx_source="test",
                fx_date="2026-08-18", data_quality="external_reference", index_method="test",
                source_url="https://example.test", license_name="CC BY 4.0", dataset_version="v1",
                signature=f"sparse-{day}", observed_at=start + timedelta(days=day), collected_at=start,
            ))
        db.commit()
        selected = select_market_history(db, "RTX3090", "24GB", start, start + timedelta(days=7))
        self.assertIsNotNone(selected)
        self.assertTrue(selected.available)
        self.assertEqual(selected.day_count, 7)
        self.assertEqual(selected.min_daily_sample_count, 1)
        metric = _historical_metric(db, start + timedelta(days=7), "RTX3090", "24GB")
        self.assertIsNotNone(metric)
        self.assertEqual(metric["volatility_7d"], 6.0)
        self.assertEqual(metric["volatility_quality"], "limited_sample")
        self.assertEqual(metric["history_coverage_status"], "complete")
        self.assertEqual(metric["history_day_count"], 7)
        self.assertEqual(metric["volatility_sources"], [HF_SOURCE])
        db.close()

    def test_archive_providers_are_stored_and_selected_as_separate_series(self):
        with tempfile.TemporaryDirectory() as folder:
            parquet = Path(folder) / "snapshot.parquet"
            connection = duckdb.connect(database=":memory:")
            connection.execute("""
                CREATE TABLE prices AS SELECT * FROM (VALUES
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'vastai', 'v1', 'A100', 1, 40, 0.40, false, true, 'ok'),
                  (TIMESTAMPTZ '2026-08-17 09:00:00+00', 'runpod', 'r1', 'A100', 1, 40, 1.40, false, true, 'ok')
                ) AS t(timestamp, provider, instance_type, gpu_type, gpu_count, gpu_memory_gb,
                       price_per_hour, is_spot, available, quality)
            """)
            connection.execute("COPY prices TO ? (FORMAT PARQUET)", [str(parquet)])
            connection.close()

            with patch("app.services.market_history_sync._cache_root", return_value=Path(folder)):
                rows = parse_hf_parquet(
                    [parquet], "test-revision", datetime(2026, 8, 18),
                    (Decimal("7"), "test fx", "2026-08-18"),
                )

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["upstream_provider"] for row in rows}, {"vast", "runpod"})
        self.assertEqual(
            {row["representative_price_cny"] for row in rows},
            {Decimal("2.800000"), Decimal("9.800000")},
        )

    def test_reimport_updates_same_observation_in_place(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        observed = datetime(2026, 8, 17, 9, 0)
        base = {
            "dataset_source": HF_SOURCE, "upstream_provider": "vast", "gpu_model": "RTX4090",
            "gpu_variant": "24GB", "billing_mode": "ondemand", "currency": "USD",
            "low_price": Decimal("0.3"), "representative_price": Decimal("0.35"), "high_price": Decimal("0.4"),
            "low_price_cny": Decimal("2.1"), "representative_price_cny": Decimal("2.45"),
            "high_price_cny": Decimal("2.8"), "sample_count": 3, "available_gpu_count": 3,
            "fx_rate": Decimal("7"), "fx_source": "test", "fx_date": "2026-08-17",
            "data_quality": "external_reference", "index_method": "test", "source_url": "https://example.test",
            "license_name": "CC BY 4.0", "dataset_version": "v1", "observed_at": observed,
            "collected_at": observed,
        }
        self.assertEqual(_store_points(db, [dict(base)]), 1)
        db.commit()
        revised = dict(base, representative_price_cny=Decimal("2.46"), dataset_version="v2")
        self.assertEqual(_store_points(db, [revised]), 0)
        db.commit()
        self.assertEqual(db.query(MarketHistoryPoint).count(), 1)
        self.assertEqual(db.query(MarketHistoryPoint).one().representative_price_cny, Decimal("2.460000"))
        db.close()

    def test_duplicate_rows_in_one_refresh_batch_are_collapsed_without_rollback(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketHistoryPoint.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        observed = datetime(2026, 8, 8, 9, 36, 21, 993447)
        base = {
            "dataset_source": HF_SOURCE, "upstream_provider": "vast", "gpu_model": "RTX6000",
            "gpu_variant": "48GB", "billing_mode": "ondemand", "currency": "USD",
            "low_price": Decimal("0.8"), "representative_price": Decimal("0.85"),
            "high_price": Decimal("0.9"), "low_price_cny": Decimal("5.6"),
            "representative_price_cny": Decimal("5.95"), "high_price_cny": Decimal("6.3"),
            "sample_count": 2, "available_gpu_count": 3, "fx_rate": Decimal("7"),
            "fx_source": "test", "fx_date": "2026-08-08", "data_quality": "external_reference",
            "index_method": "cross_listing_iqr_median_per_gpu_hour",
            "source_url": "https://example.test/a.parquet", "license_name": "CC BY 4.0",
            "dataset_version": "v1", "observed_at": observed, "collected_at": observed,
        }
        stronger = dict(
            base,
            sample_count=4,
            available_gpu_count=6,
            representative_price=Decimal("0.86"),
            representative_price_cny=Decimal("6.02"),
            source_url="https://example.test/b.parquet",
        )
        self.assertEqual(_store_points(db, [base, stronger, dict(base)]), 1)
        db.commit()
        stored = db.query(MarketHistoryPoint).one()
        self.assertEqual(stored.sample_count, 4)
        self.assertEqual(stored.representative_price_cny, Decimal("6.020000"))
        db.close()


if __name__ == "__main__":
    unittest.main()
