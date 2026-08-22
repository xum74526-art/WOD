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
from app.models.market_price import MarketCandleSyncStatus, MarketHistoryPoint, MarketPriceCandle, MarketPriceSnapshot
from app.routers.market import _historical_metric, price_candles
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
        for day in range(7):
            candle_open = Decimal("2.0") + Decimal(day) / Decimal("100")
            candle_close = candle_open + Decimal("0.005")
            db.add(MarketPriceCandle(
                source="kai", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                start_time=start + timedelta(days=day), end_time=start + timedelta(days=day + 1),
                open_price_cny=candle_open, high_price_cny=candle_close + Decimal("0.05"),
                low_price_cny=candle_open - Decimal("0.05"), close_price_cny=candle_close,
                sample_count=1, observation_count=1, method="official_ohlc", data_quality="official",
                source_version="v1", signature=f"stored-candle-{day}", source_observed_at=now,
                collected_at=now, updated_at=now,
            ))
        db.add(MarketCandleSyncStatus(
            source="kai", status="ok", refresh_seconds=300, model_count=1, candle_count=7,
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
        self.assertEqual(payload["latest_live_price_cny"], 2.06)
        self.assertTrue(payload["latest_live_comparable_to_history"])
        self.assertLess(max(candle["high_price_cny"] for candle in payload["candles"]), 3)
        self.assertEqual({source for candle in payload["candles"] for source in candle["sources"]}, {"kai"})
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
