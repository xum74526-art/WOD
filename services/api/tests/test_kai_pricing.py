import asyncio
from concurrent.futures import ThreadPoolExecutor
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
import time
from threading import Lock
from unittest.mock import patch

from app.integrations.kai_pricing import (
    _CANDLE_EXECUTOR,
    _CANDLE_WORKERS,
    _HTTP_RUNNER,
    _get_json,
    _select_centered_price_candidates,
    _upstream_gpu_model_filters,
    KaiPricingError,
    KaiPriceBatch,
    clear_caches,
    fetch_price_batch,
    get_aggregated_candles,
    get_exact_product_candles,
    get_ranking_metrics,
    normalized_current_quotes,
)
from app.core.config import settings


def quote(
    product_id="kai-4090-a",
    *,
    status="current",
    quantities=(1, 2),
    price="2.5",
    gpu_name="RTX 4090",
    gpu_model="RTX 4090 24GB",
    vram="24GB",
):
    return {
        "productId": product_id,
        "gpuName": gpu_name,
        "gpuModel": gpu_model,
        "vram": vram,
        "region": "CN-East",
        "availability": {"status": "available"},
        "gpuCountOptions": list(quantities),
        "currency": "CNY",
        "unit": "GPU_HOUR",
        "priceCny": price,
        "priceStatus": status,
    }


class KaiPricingTests(unittest.TestCase):
    def setUp(self):
        clear_caches()
        self.now = datetime(2026, 8, 21, 4)

    def batch(self, rows):
        return KaiPriceBatch(
            quotes=tuple(rows), observed_at=self.now,
            valid_until=self.now + timedelta(minutes=5),
            data_version=2, refresh_interval_ms=300_000, raw_count=len(rows),
        )

    def history_payload(
        self, product_id, *, base="2.4", count=169, interval="1h", end_at=None,
    ):
        base_value = Decimal(base)
        interval_hours = {"1h": 1, "4h": 4, "1d": 24}[interval]
        interval_ms = interval_hours * 60 * 60 * 1000
        candles = []
        last_observed = end_at or self.now
        first_observed = last_observed - timedelta(hours=interval_hours * max(count - 1, 0))
        for index in range(count):
            observed = first_observed + timedelta(hours=interval_hours * index)
            candles.append({
                "asOf": observed.isoformat() + "Z",
                "open": str(base_value), "high": str(base_value + Decimal("0.2")),
                "low": str(base_value - Decimal("0.1")),
                "close": str(base_value + Decimal("0.1")),
            })
        return {
            "data": {
                "productId": product_id, "currency": "CNY", "unit": "GPU_HOUR",
                "interval": interval, "months": 1, "candles": candles,
            },
            "meta": {
                "asOf": last_observed.isoformat() + "Z", "dataVersion": 2,
                "count": len(candles), "interval": interval, "intervalMs": interval_ms,
                "months": 1,
                "from": (last_observed - timedelta(days=31)).isoformat() + "Z",
                "to": last_observed.isoformat() + "Z",
            },
        }

    def test_only_current_available_quotes_are_mapped_and_quantity_is_not_inventory(self):
        rows = normalized_current_quotes(self.batch([
            quote(),
            quote("delayed", status="delayed"),
            quote("empty-options", quantities=()),
        ]))
        self.assertEqual([item["external_product_id"] for item in rows], ["kai-4090-a", "empty-options"])
        self.assertEqual(rows[0]["max_configurable_quantity"], 2)
        self.assertEqual(rows[0]["gpu_count_options"], (1, 2))
        self.assertIsNone(rows[1]["max_configurable_quantity"])
        self.assertNotIn("stock", rows[0])

    def test_centered_price_cap_preserves_full_pool_median_for_ten_quotes(self):
        rows = [{
            "external_product_id": f"product-{11 - price:02d}",
            "price_cny": Decimal(price),
        } for price in range(1, 11)]

        selected = _select_centered_price_candidates(rows, 8)

        selected_prices = sorted(item["price_cny"] for item in selected)
        self.assertEqual(selected_prices, [Decimal(value) for value in range(2, 10)])
        self.assertEqual(
            (selected_prices[3] + selected_prices[4]) / Decimal("2"),
            Decimal("5.5"),
        )

    def test_centered_price_candidate_selection_ignores_input_order(self):
        rows = [{
            "external_product_id": f"product-{11 - price:02d}",
            "price_cny": Decimal(price),
        } for price in range(1, 11)]

        first = _select_centered_price_candidates(rows, 8)
        second = _select_centered_price_candidates(reversed(rows), 8)

        self.assertEqual(
            [item["external_product_id"] for item in first],
            [item["external_product_id"] for item in second],
        )

    def test_centered_price_cohort_reduces_single_product_cross_rank_jump(self):
        prices = [
            ("product-j", Decimal("2.20")),
            ("product-i", Decimal("2.35")),
            ("product-h", Decimal("3.00")),
            ("product-g", Decimal("3.52")),
            ("product-f", Decimal("4.49")),
            ("product-e", Decimal("5.62")),
            ("product-d", Decimal("6.38")),
            ("product-c", Decimal("6.71")),
            ("product-b", Decimal("7.64")),
            ("product-a", Decimal("7.70")),
        ]
        rows = [quote(product_id, price=str(price)) for product_id, price in prices]
        prices_by_id = dict(prices)

        def history(product_id, interval, _months=1, *, deadline=None):
            self.assertEqual(interval, "1h")
            candles = []
            first_observed = self.now - timedelta(hours=168)
            for index in range(169):
                observed = first_observed + timedelta(hours=index)
                if product_id == "product-d":
                    previous = Decimal("5.43") if index <= 84 else Decimal("6.38")
                    current = Decimal("5.43") if index < 84 else Decimal("6.38")
                else:
                    previous = current = prices_by_id[product_id]
                candles.append({
                    "asOf": observed.isoformat() + "Z",
                    "open": str(previous),
                    "high": str(max(previous, current)),
                    "low": str(min(previous, current)),
                    "close": str(current),
                })
            return ({
                "data": {
                    "productId": product_id, "currency": "CNY", "unit": "GPU_HOUR",
                    "interval": "1h", "months": 1, "candles": candles,
                },
                "meta": {
                    "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
                    "count": len(candles), "interval": "1h", "intervalMs": 3_600_000,
                    "months": 1,
                    "from": (self.now - timedelta(days=31)).isoformat() + "Z",
                    "to": self.now.isoformat() + "Z",
                },
            }, 1000)

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ), patch.object(settings, "KAI_CANDLE_MAX_PRODUCTS", 8):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        closes = [Decimal(str(item["close_price_cny"])) for item in value["candles"]]
        observed_max_jump = max(
            abs(current / previous - Decimal("1"))
            for previous, current in zip(closes, closes[1:])
        )
        legacy_ids = {
            product_id for product_id, _price in sorted(prices)[:8]
        }
        legacy_before = sorted(
            Decimal("5.43") if product_id == "product-d" else price
            for product_id, price in prices if product_id in legacy_ids
        )
        legacy_after = sorted(
            Decimal("6.38") if product_id == "product-d" else price
            for product_id, price in prices if product_id in legacy_ids
        )
        legacy_before_median = (legacy_before[3] + legacy_before[4]) / Decimal("2")
        legacy_after_median = (legacy_after[3] + legacy_after[4]) / Decimal("2")
        legacy_jump = abs(legacy_after_median / legacy_before_median - Decimal("1"))

        self.assertGreater(legacy_jump, Decimal("0.08"))
        self.assertLess(observed_max_jump, Decimal("0.025"))
        self.assertLess(observed_max_jump, legacy_jump / Decimal("3"))
        self.assertEqual(value["provenance"]["candidate_product_count"], 10)
        self.assertEqual(value["provenance"]["sampled_candidate_product_count"], 8)
        self.assertEqual(
            value["provenance"]["candidate_sampling_method"],
            "current_price_centered_parity_matched",
        )
        self.assertEqual(value["latest_live_price_cny"], 5.055)
        self.assertTrue(value["latest_live_comparable_to_history"])

    def test_live_comparability_uses_full_pool_and_successful_cohort_medians(self):
        rows = [
            quote("product-a", price="2"),
            quote("product-b", price="4"),
            quote("product-c", price="6"),
        ]

        def history(product_id, _interval, _months=1, *, deadline=None):
            if product_id == "product-c":
                raise KaiPricingError("history_unavailable")
            return self.history_payload(product_id, base=str({"product-a": 2, "product-b": 4}[product_id])), 1000

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(value["latest_live_price_cny"], 4.0)
        self.assertFalse(value["latest_live_comparable_to_history"])
        self.assertEqual(
            value["provenance"]["latest_live_successful_cohort_median_price_cny"],
            3.0,
        )

    def test_late_low_price_product_cannot_change_members_mid_window(self):
        full_history_prices = {
            "product-low-a": "73.4",
            "product-low-b": "73.4",
            "product-low-c": "73.4",
            "product-high-a": "126.4",
            "product-high-b": "126.4",
            "product-high-c": "126.4",
        }
        late_product_id = "product-late-low"
        rows = [
            quote(product_id, price=str(Decimal(base) + Decimal("0.1")))
            for product_id, base in full_history_prices.items()
        ] + [quote(late_product_id, price="73.5")]

        def history(product_id, interval, _months=1, *, deadline=None):
            self.assertEqual(interval, "1h")
            if product_id == late_product_id:
                # This lower-price region joined halfway through the requested
                # range. It is real history, but it cannot join the aggregate
                # halfway and change the meaning of the median.
                return self.history_payload(
                    product_id, base="73.4", count=85, interval=interval,
                ), 1000
            return self.history_payload(
                product_id,
                base=full_history_prices[product_id],
                count=169,
                interval=interval,
            ), 1000

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        closes = [Decimal(str(item["close_price_cny"])) for item in value["candles"]]
        observed_jumps = [
            abs(current / previous - Decimal("1"))
            for previous, current in zip(closes, closes[1:])
        ]
        legacy_before = [
            Decimal(base) + Decimal("0.1")
            for base in full_history_prices.values()
        ]
        legacy_after = legacy_before + [Decimal("73.5")]
        legacy_before.sort()
        legacy_after.sort()
        legacy_before_median = (
            legacy_before[2] + legacy_before[3]
        ) / Decimal("2")
        legacy_after_median = legacy_after[3]
        legacy_jump = abs(
            legacy_after_median / legacy_before_median - Decimal("1")
        )
        expected_ids = sorted(full_history_prices)
        self.assertGreater(legacy_jump, Decimal("0.26"))
        self.assertEqual(value["coverage_class"], "full")
        self.assertEqual(len(value["candles"]), 168)
        self.assertEqual({item["sample_count"] for item in value["candles"]}, {6})
        self.assertEqual({item["observation_count"] for item in value["candles"]}, {6})
        self.assertEqual(max(observed_jumps), Decimal("0"))
        self.assertEqual(value["provenance"]["selected_product_ids"], expected_ids)
        self.assertEqual(value["provenance"]["fixed_cohort_product_ids"], expected_ids)
        self.assertEqual(value["provenance"]["fixed_cohort_product_count"], 6)
        self.assertEqual(
            value["provenance"]["fixed_cohort_window_start"],
            (self.now - timedelta(days=7)).isoformat(timespec="seconds") + "Z",
        )
        self.assertNotIn(late_product_id, value["provenance"]["fixed_cohort_product_ids"])
        self.assertFalse(value["latest_live_comparable_to_history"])
        self.assertEqual(
            value["provenance"]["latest_live_full_pool_median_price_cny"],
            73.5,
        )
        self.assertEqual(
            value["provenance"]["latest_live_successful_cohort_median_price_cny"],
            100.0,
        )

    def test_seven_day_candles_use_official_ohlc_and_are_cached(self):
        batch = self.batch([quote()])
        candles = []
        for index in range(169):
            observed = self.now - timedelta(days=7) + timedelta(hours=index)
            base = Decimal("2.0") + Decimal(index) / Decimal("100")
            candles.append({
                "asOf": observed.isoformat() + "Z",
                "open": str(base), "high": str(base + Decimal("0.08")),
                "low": str(base - Decimal("0.04")), "close": str(base + Decimal("0.02")),
            })
        payload = {
            "data": {
                "productId": "kai-4090-a", "currency": "CNY", "unit": "GPU_HOUR",
                "interval": "1h", "months": 1,
                "candles": candles,
            },
            "meta": {
                "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
                "count": len(candles), "interval": "1h", "intervalMs": 3_600_000,
                "months": 1,
                "from": (self.now - timedelta(days=31)).isoformat() + "Z",
                "to": self.now.isoformat() + "Z",
            },
        }
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles",
            return_value=(payload, 1000),
        ) as fetch:
            first = get_aggregated_candles("RTX4090", "24GB", "7d")
            second = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first["selected_source"], "kai")
        self.assertEqual(first["method"], "kai_official_ohlc_cross_region_robust_median")
        self.assertEqual(first["coverage_class"], "full")
        self.assertEqual(first["bucket_seconds"], 60 * 60)
        self.assertEqual(len(first["candles"]), 168)
        self.assertEqual(first["coverage_span_hours"], 168.0)
        self.assertEqual(first["provenance"]["history_as_of"], "2026-08-21T04:00:00Z")
        self.assertEqual(first["provenance"]["history_lag_seconds"], 0)
        self.assertEqual(first["provenance"]["selected_product_ids"], ["kai-4090-a"])
        self.assertGreater(first["candles"][0]["high_price_cny"], first["candles"][0]["low_price_cny"])
        self.assertTrue(all(item["sources"] == ["kai"] for item in first["candles"]))

    def test_one_upstream_decimal_ulp_is_normalized_without_losing_history(self):
        batch = self.batch([quote()])
        payload = self.history_payload("kai-4090-a", count=169, interval="1h")
        payload["data"]["candles"][20]["high"] = "2.499999"

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles",
            return_value=(payload, 1000),
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(value["coverage_class"], "full")
        self.assertEqual(len(value["candles"]), 168)
        self.assertTrue(all(
            item["high_price_cny"] >= max(item["open_price_cny"], item["close_price_cny"])
            for item in value["candles"]
        ))

    def test_twenty_four_hour_window_is_anchored_to_last_official_candle(self):
        batch = self.batch([quote()])
        last_official_start = self.now - timedelta(hours=12)
        payload = self.history_payload(
            "kai-4090-a", count=745, interval="1h", end_at=last_official_start,
        )
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 180_000),
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "24h")

        self.assertEqual(value["bucket_seconds"], 60 * 60)
        self.assertEqual(len(value["candles"]), 24)
        self.assertEqual(value["coverage_class"], "full")
        self.assertEqual(value["coverage_span_hours"], 24.0)
        self.assertEqual(
            value["candles"][-1]["end_time"],
            last_official_start.isoformat() + "Z",
        )
        self.assertEqual(
            value["provenance"]["history_as_of"],
            last_official_start.isoformat() + "Z",
        )
        self.assertEqual(value["provenance"]["history_lag_seconds"], 12 * 60 * 60)
        self.assertLessEqual(
            datetime.fromisoformat(value["provenance"]["history_as_of"].removesuffix("Z")),
            datetime.fromisoformat(payload["meta"]["to"].removesuffix("Z")),
        )

    def test_ninety_day_candles_request_three_official_months(self):
        batch = self.batch([quote()])
        candles = []
        for index in range(91):
            observed = self.now - timedelta(days=90) + timedelta(days=index)
            base = Decimal("2.0") + Decimal(index) / Decimal("100")
            candles.append({
                "asOf": observed.isoformat() + "Z",
                "open": str(base), "high": str(base + Decimal("0.08")),
                "low": str(base - Decimal("0.04")), "close": str(base + Decimal("0.02")),
            })
        payload = {
            "data": {
                "productId": "kai-4090-a", "currency": "CNY", "unit": "GPU_HOUR",
                "interval": "1d", "months": 3, "candles": candles,
            },
            "meta": {
                "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
                "count": len(candles), "interval": "1d", "intervalMs": 86_400_000,
                "months": 3,
                "from": (self.now - timedelta(days=93)).isoformat() + "Z",
                "to": self.now.isoformat() + "Z",
            },
        }
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 4000),
        ) as fetch:
            value = get_aggregated_candles("RTX4090", "24GB", "90d")

        self.assertEqual(fetch.call_args.args[2], 3)
        self.assertEqual(value["range"], "90d")
        self.assertEqual(value["coverage_class"], "full")
        self.assertEqual(len(value["candles"]), 90)
        self.assertEqual(value["coverage_span_hours"], 90 * 24)

    def test_thirty_day_chart_uses_native_four_hour_candles(self):
        batch = self.batch([quote()])
        payload = self.history_payload(
            "kai-4090-a", count=187, interval="4h",
        )
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 46_000),
        ) as fetch:
            value = get_aggregated_candles("RTX4090", "24GB", "30d")

        self.assertEqual(fetch.call_args.args[1:3], ("4h", 1))
        self.assertEqual(value["bucket_seconds"], 4 * 60 * 60)
        self.assertEqual(len(value["candles"]), 180)
        self.assertEqual(value["coverage_span_hours"], 30 * 24)
        self.assertEqual(value["coverage_class"], "full")

    def test_exact_product_candles_match_identity_and_live_price(self):
        batch = self.batch([quote()])
        candles = []
        for index in range(169):
            observed = self.now - timedelta(days=7) + timedelta(hours=index)
            candles.append({
                "asOf": observed.isoformat() + "Z",
                "open": "2.4", "high": "2.6", "low": "2.3", "close": "2.5",
            })
        payload = {
            "data": {
                "productId": "kai-4090-a", "currency": "CNY", "unit": "GPU_HOUR",
                "interval": "1h", "months": 1, "candles": candles,
            },
            "meta": {
                "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
                "count": len(candles), "interval": "1h", "intervalMs": 3_600_000,
                "months": 1,
                "from": (self.now - timedelta(days=31)).isoformat() + "Z",
                "to": self.now.isoformat() + "Z",
            },
        }
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 1000),
        ):
            exact = get_exact_product_candles("kai-4090-a", "RTX4090", "24GB", "7d")
            with self.assertRaises(KaiPricingError) as mismatch:
                get_exact_product_candles("kai-4090-a", "A100", "80GB", "7d")

        self.assertEqual(exact["method"], "kai_official_exact_product_ohlc")
        self.assertEqual(exact["coverage_class"], "full")
        self.assertEqual(exact["bucket_seconds"], 60 * 60)
        self.assertEqual(len(exact["candles"]), 168)
        self.assertEqual(exact["latest_live_price_cny"], 2.5)
        self.assertEqual(exact["provenance"]["product_selection"], "exact_product_id")
        self.assertEqual(mismatch.exception.code, "product_identity_mismatch")

    def test_ranking_cap_covers_twenty_identities_with_official_metrics(self):
        identities = {(f"GPU{index:02d}", "24GB") for index in range(20)}
        quotes = [{
            "external_product_id": f"product-{index:02d}",
            "gpu_model": f"GPU{index:02d}", "gpu_variant": "24GB",
            "price_cny": Decimal("2.5"), "max_configurable_quantity": 1,
        } for index in range(20)]

        def history(product_id, interval, _months=1, *, deadline=None):
            candles = []
            for index in range(43):
                observed = self.now - timedelta(days=7) + timedelta(hours=4 * index)
                candles.append({
                    "asOf": observed.isoformat() + "Z",
                    "open": "2.4", "high": "2.6", "low": "2.3", "close": "2.5",
                })
            return ({
                "data": {
                    "productId": product_id, "currency": "CNY", "unit": "GPU_HOUR",
                    "interval": interval, "months": 1, "candles": candles,
                },
                "meta": {
                    "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
                    "count": len(candles), "interval": interval, "intervalMs": 14_400_000,
                    "months": 1,
                    "from": (self.now - timedelta(days=31)).isoformat() + "Z",
                    "to": self.now.isoformat() + "Z",
                },
            }, 1000)

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch([])), patch(
            "app.integrations.kai_pricing.normalized_current_quotes", return_value=quotes,
        ), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ) as fetch, patch.object(settings, "KAI_RANKING_MAX_PRODUCTS", 24):
            metrics = get_ranking_metrics(identities)

        self.assertEqual(len(metrics), 20)
        self.assertEqual({call.args[1] for call in fetch.call_args_list}, {"4h"})
        self.assertTrue(all(item["volatility_status"] == "available" for item in metrics.values()))
        self.assertTrue(all(item["history_provenance"]["upstream_provider"] == "kai" for item in metrics.values()))

    def test_model_price_lookup_uses_small_exact_upstream_filter(self):
        payload = {
            "data": [],
            "meta": {
                "asOf": self.now.isoformat() + "Z",
                "validUntil": (self.now + timedelta(minutes=5)).isoformat() + "Z",
                "count": 0, "dataVersion": 2, "refreshIntervalMs": 300_000,
            },
        }
        with patch("app.integrations.kai_pricing.utcnow", return_value=self.now), patch(
            "app.integrations.kai_pricing._get_json", return_value=(payload, 200),
        ) as get_json:
            batch = fetch_price_batch(
                use_cache=False,
                gpu_models=("RTX 4090 24GB",),
                deadline=time.monotonic() + 1,
            )

        self.assertEqual(batch.raw_count, 0)
        path = get_json.call_args.args[0]
        self.assertIn("gpuModel=RTX+4090+24GB", path)
        self.assertNotEqual(path, "/v1/prices")

    def test_price_batch_accepts_v24_meta_without_refresh_interval(self):
        row = {
            **quote(), "id": "kai-4090-a",
            "asOf": self.now.isoformat() + "Z", "dataVersion": 24,
        }
        payload = {
            "data": [row],
            "meta": {
                "asOf": self.now.isoformat() + "Z",
                "effectiveAt": self.now.isoformat() + "Z",
                "snapshotId": "snapshot-v24",
                "validUntil": (self.now + timedelta(minutes=5)).isoformat() + "Z",
                "count": 1,
                "dataVersion": 24,
            },
        }
        with patch("app.integrations.kai_pricing.utcnow", return_value=self.now), patch(
            "app.integrations.kai_pricing._get_json", return_value=(payload, 500),
        ):
            batch = fetch_price_batch(use_cache=False)

        self.assertEqual(batch.data_version, 24)
        self.assertEqual(batch.refresh_interval_ms, 300_000)
        self.assertEqual(batch.raw_count, 1)

    def test_price_batch_rejects_missing_refresh_with_invalid_validity_window(self):
        payload = {
            "data": [],
            "meta": {
                "asOf": self.now.isoformat() + "Z",
                "validUntil": (self.now + timedelta(hours=1)).isoformat() + "Z",
                "count": 0,
                "dataVersion": 24,
            },
        }
        with patch("app.integrations.kai_pricing.utcnow", return_value=self.now), patch(
            "app.integrations.kai_pricing._get_json", return_value=(payload, 300),
        ):
            with self.assertRaises(KaiPricingError) as raised:
                fetch_price_batch(use_cache=False)

        self.assertEqual(raised.exception.code, "upstream_invalid_response")

    def test_documented_gpu_model_aliases_match_real_kai_display_names(self):
        expected = {
            ("H100", "94GB"): ("H100 NVL", "H100 NVL 94GB", "94GB"),
            ("L40S", "45GB"): ("L40S", "L40S 44.7GB", "44.7GB"),
            ("RTX2000", "16GB"): ("RTX 2000 Ada", "RTX 2000 Ada 16GB", "16GB"),
            ("RTX4000", "20GB"): ("RTX 4000 Ada", "RTX 4000 Ada 20GB", "20GB"),
            ("RTX4000", "24GB"): ("RTX PRO 4000 Blackwell", "RTX PRO 4000 Blackwell 24GB", "24GB"),
            ("RTX4070SUPER", "16GB"): ("RTX 4070 SUPER Ti", "RTX 4070 SUPER Ti 16GB", "16GB"),
            ("RTX4500", "24GB"): ("RTX 4500 Ada", "RTX 4500 Ada 24GB", "24GB"),
            ("RTX4500", "32GB"): ("RTX PRO 4500 Blackwell", "RTX PRO 4500 Blackwell 32GB", "32GB"),
            ("RTX5000", "32GB"): ("RTX 5000 Ada", "RTX 5000 Ada 32GB", "32GB"),
            ("RTX5000", "48GB"): ("RTX PRO 5000", "RTX PRO 5000 48GB", "48GB"),
            ("RTX5880", "48GB"): ("RTX 5880 Ada", "RTX 5880 Ada 48GB", "48GB"),
            ("RTX6000", "24GB"): ("Quadro RTX 6000", "Quadro RTX 6000 24GB", "24GB"),
            ("RTX6000", "48GB"): ("RTX 6000 Ada", "RTX 6000 Ada 48GB", "48GB"),
        }
        fixtures = []
        for index, (identity, (gpu_name, upstream_name, vram)) in enumerate(expected.items()):
            fixtures.append(quote(
                f"alias-{index}", gpu_name=gpu_name, gpu_model=upstream_name, vram=vram,
            ))
        normalized = {
            item["external_product_id"]: (item["gpu_model"], item["gpu_variant"])
            for item in normalized_current_quotes(self.batch(fixtures))
        }
        for index, (identity, (_gpu_name, upstream_name, _vram)) in enumerate(expected.items()):
            with self.subTest(identity=identity):
                self.assertIn(upstream_name, _upstream_gpu_model_filters(*identity))
                self.assertEqual(normalized[f"alias-{index}"], identity)

    def test_partial_h20_history_renders_but_never_becomes_a_seven_day_metric(self):
        h20 = quote(
            "kai-h20-a",
            gpu_name="H20",
            gpu_model="H20 141GB",
            vram="141GB",
            price="3.1",
            quantities=(),
        )
        batch = self.batch([h20])
        def partial_history(product_id, interval, _months=1, *, deadline=None):
            return self.history_payload(
                product_id, base="3.0", count=8, interval=interval,
            ), 1000

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=partial_history,
        ):
            exact = get_exact_product_candles("kai-h20-a", "H20", "141GB", "7d")
            clear_caches()
            general = get_aggregated_candles("H20", "141GB", "7d")
            clear_caches()
            ranking = get_ranking_metrics({("H20", "141GB")})

        for value in (exact, general):
            self.assertEqual(value["coverage_class"], "partial")
            self.assertEqual(value["curve_status"], "partial")
            self.assertEqual(value["history_coverage_status"], "partial")
            self.assertEqual(value["data_quality"], "official_historical_ohlc_partial")
            self.assertEqual(value["coverage_span_hours"], 7.0)
            self.assertEqual(len(value["candles"]), 7)
            for forbidden in ("change_7d_pct", "volatility_7d", "range_low_cny", "range_high_cny"):
                self.assertNotIn(forbidden, value)
        partial = ranking[("H20", "141GB")]
        self.assertIsNone(partial["change_7d_pct"])
        self.assertIsNone(partial["volatility_7d"])
        self.assertIsNone(partial["range_low_cny"])
        self.assertIsNone(partial["range_high_cny"])
        self.assertEqual(partial["history_coverage_status"], "partial")
        self.assertEqual(partial["history_day_count"], 2)
        self.assertEqual(partial["history_point_count"], 7)
        self.assertLess(partial["observed_partial_low_cny"], partial["observed_partial_high_cny"])

    def test_single_official_observation_is_returned_without_zero_percent_claim(self):
        row = quote("single")
        batch = self.batch([row])
        # KAI includes the open bucket at meta.to, so two publications contain
        # exactly one closed official candle.
        payload = self.history_payload("single", count=2)
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=batch), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 500),
        ):
            exact = get_exact_product_candles("single", "RTX4090", "24GB", "7d")
            clear_caches()
            general = get_aggregated_candles("RTX4090", "24GB", "7d")

        for value in (exact, general):
            self.assertEqual(value["coverage_class"], "single")
            self.assertEqual(value["curve_status"], "single")
            self.assertEqual(value["history_coverage_status"], "single")
            self.assertEqual(value["coverage_span_hours"], 1.0)
            self.assertEqual(len(value["candles"]), 1)
            self.assertNotIn("change_7d_pct", value)

    def test_price_batch_rejects_duplicate_or_mismatched_row_identity(self):
        valid_row = {
            **quote(), "id": "kai-4090-a",
            "asOf": self.now.isoformat() + "Z", "dataVersion": 2,
        }

        def payload(rows):
            return {
                "data": rows,
                "meta": {
                    "asOf": self.now.isoformat() + "Z",
                    "validUntil": (self.now + timedelta(minutes=5)).isoformat() + "Z",
                    "count": len(rows), "dataVersion": 2, "refreshIntervalMs": 300_000,
                },
            }

        invalid_batches = [
            [valid_row, dict(valid_row)],
            [{**valid_row, "id": "different-id"}],
            [{**valid_row, "dataVersion": 1}],
            [{**valid_row, "asOf": (self.now - timedelta(minutes=5)).isoformat() + "Z"}],
        ]
        for rows in invalid_batches:
            clear_caches()
            with self.subTest(rows=rows), patch(
                "app.integrations.kai_pricing.utcnow", return_value=self.now,
            ), patch(
                "app.integrations.kai_pricing._get_json", return_value=(payload(rows), 500),
            ):
                with self.assertRaises(KaiPricingError) as raised:
                    fetch_price_batch(use_cache=False, gpu_models=("RTX 4090 24GB",))
                self.assertEqual(raised.exception.code, "upstream_invalid_response")

    def test_official_ohlc_must_have_unique_consecutive_intervals(self):
        rows = [quote()]
        for mutation in ("duplicate", "gap"):
            clear_caches()
            payload = self.history_payload("kai-4090-a")
            if mutation == "duplicate":
                payload["data"]["candles"][8]["asOf"] = payload["data"]["candles"][7]["asOf"]
            else:
                payload["data"]["candles"].pop(8)
                payload["meta"]["count"] -= 1
            with self.subTest(mutation=mutation), patch(
                "app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows),
            ), patch(
                "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 1000),
            ):
                with self.assertRaises(KaiPricingError) as raised:
                    get_aggregated_candles("RTX4090", "24GB", "7d")
                self.assertEqual(raised.exception.code, "history_unavailable")

    def test_future_official_metadata_is_rejected(self):
        payload = self.history_payload("kai-4090-a")
        future = self.now + timedelta(hours=1)
        payload["meta"]["asOf"] = future.isoformat() + "Z"
        payload["meta"]["to"] = future.isoformat() + "Z"
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch([quote()])), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 1000),
        ), patch("app.integrations.kai_pricing.utcnow", return_value=self.now):
            with self.assertRaises(KaiPricingError) as raised:
                get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(raised.exception.code, "history_unavailable")

    def test_complete_but_stale_official_window_is_observable_and_not_full(self):
        stale_end = self.now - timedelta(days=3)
        payload = self.history_payload(
            "kai-4090-a", count=169, interval="1h", end_at=stale_end,
        )
        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch([quote()])), patch(
            "app.integrations.kai_pricing._fetch_product_candles", return_value=(payload, 1000),
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(len(value["candles"]), 168)
        self.assertEqual(value["coverage_class"], "partial")
        self.assertEqual(value["history_status"], "partial_history")
        self.assertEqual(value["history_coverage_status"], "partial")
        self.assertEqual(value["provenance"]["raw_coverage_class"], "full")
        self.assertEqual(value["provenance"]["history_freshness_status"], "stale")
        self.assertGreater(
            value["provenance"]["history_lag_seconds"],
            value["provenance"]["history_stale_after_seconds"],
        )

    def test_latest_majority_cohort_ignores_one_stale_region(self):
        rows = [quote("product-a"), quote("product-b"), quote("product-stale")]

        def history(product_id, _interval, _months=1, *, deadline=None):
            end_at = self.now - timedelta(days=3) if product_id == "product-stale" else self.now
            return self.history_payload(product_id, count=169, interval="1h", end_at=end_at), 1000

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(value["coverage_class"], "full")
        self.assertEqual(len(value["candles"]), 168)
        self.assertEqual(
            value["provenance"]["selected_product_ids"],
            ["product-a", "product-b"],
        )
        self.assertEqual(value["provenance"]["validated_product_count"], 3)
        self.assertEqual(value["provenance"]["cohort_min_product_count"], 2)
        self.assertEqual(value["provenance"]["selection_completeness"], "latest_reasonable_cohort")
        self.assertEqual(value["provenance"]["history_freshness_status"], "current")

    def test_absolute_deadline_covers_slow_filtered_price_batch(self):
        def slow_batch(**_kwargs):
            time.sleep(0.12)
            return self.batch([quote()])

        started = time.monotonic()
        with patch("app.integrations.kai_pricing.fetch_price_batch", side_effect=slow_batch), patch.object(
            settings, "KAI_CANDLE_TOTAL_TIMEOUT", 0.03,
        ):
            with self.assertRaises(KaiPricingError) as raised:
                get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(raised.exception.code, "upstream_timeout")
        self.assertLessEqual(time.monotonic() - started, 0.18)

    def test_sub_minimum_remaining_budget_never_starts_http_request(self):
        with patch.object(_HTTP_RUNNER, "request") as request:
            with self.assertRaises(KaiPricingError) as raised:
                _get_json(
                    "/v1/prices?gpuModel=RTX+4090+24GB",
                    timeout=5,
                    max_bytes=1024,
                    deadline=time.monotonic() + 0.05,
                )

        self.assertEqual(raised.exception.code, "upstream_timeout")
        request.assert_not_called()

    def test_http_deadline_covers_slow_connect_and_stream_phases(self):
        async def slow_two_phase(_client, _url, _max_bytes, _timeout):
            await asyncio.sleep(0.15)  # connect/headers
            await asyncio.sleep(0.15)  # body streaming
            return ({"ok": True}, 12)

        started = time.monotonic()
        with patch.object(_HTTP_RUNNER, "_request", side_effect=slow_two_phase):
            with self.assertRaises(KaiPricingError) as raised:
                _get_json(
                    "/v1/prices?gpuModel=RTX+4090+24GB",
                    timeout=5,
                    max_bytes=1024,
                    deadline=started + 0.20,
                )
        elapsed = time.monotonic() - started

        self.assertEqual(raised.exception.code, "upstream_timeout")
        self.assertLessEqual(elapsed, 0.25)  # deadline + Windows scheduler tolerance
        until = time.monotonic() + 0.5
        while _HTTP_RUNNER.active_count and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(_HTTP_RUNNER.active_count, 0)
        self.assertEqual(_HTTP_RUNNER.pending_count, 0)

    def test_cancellation_resistance_keeps_generation_recovery_bounded(self):
        actual_lock = Lock()
        actual_active = 0
        actual_peak = 0
        initial_snapshot = _HTTP_RUNNER.snapshot()
        observed_snapshots = []

        async def cancellation_resistant(_client, _url, _max_bytes, _timeout):
            nonlocal actual_active, actual_peak
            with actual_lock:
                actual_active += 1
                actual_peak = max(actual_peak, actual_active)
            try:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    # Model a transport that needs time to close a response
                    # after cancellation.  Admission must remain occupied.
                    await asyncio.sleep(0.25)
                return ({"ok": True}, 12)
            finally:
                with actual_lock:
                    actual_active -= 1

        def one_call():
            try:
                _get_json(
                    "/v1/prices?gpuModel=RTX+4090+24GB",
                    timeout=5,
                    max_bytes=1024,
                    deadline=time.monotonic() + 0.12,
                )
            except KaiPricingError:
                return

        with patch.object(_HTTP_RUNNER, "_request", side_effect=cancellation_resistant):
            for _ in range(3):
                with ThreadPoolExecutor(max_workers=_HTTP_RUNNER.max_pending) as executor:
                    list(executor.map(lambda _index: one_call(), range(_HTTP_RUNNER.max_pending)))
                observed_snapshots.append(_HTTP_RUNNER.snapshot())

        until = time.monotonic() + 1
        while time.monotonic() < until:
            with actual_lock:
                all_requests_finished = actual_active == 0
            if all_requests_finished and _HTTP_RUNNER.snapshot()["retired_generation_count"] == 0:
                break
            time.sleep(0.01)
        final_snapshot = _HTTP_RUNNER.snapshot()
        # Recovery is allowed to overlap one retired pool with the replacement
        # pool.  It must never create an unbounded chain of generations.
        self.assertLessEqual(actual_peak, _HTTP_RUNNER.max_pending * 2)
        self.assertLessEqual(_HTTP_RUNNER.peak_active, _HTTP_RUNNER.max_pending * 2)
        self.assertTrue(all(item["retired_generation_count"] <= 1 for item in observed_snapshots))
        self.assertLessEqual(
            final_snapshot["restart_count"] - initial_snapshot["restart_count"],
            2,
        )
        self.assertEqual(actual_active, 0)
        self.assertEqual(_HTTP_RUNNER.active_count, 0)
        self.assertEqual(_HTTP_RUNNER.pending_count, 0)
        self.assertEqual(final_snapshot["retired_generation_count"], 0)

    def test_one_slow_region_keeps_fast_official_region_and_executor_is_bounded(self):
        rows = [quote("product-a"), quote("product-b")]

        def history(product_id, _interval, _months=1, *, deadline=None):
            if product_id == "product-a":
                time.sleep(0.18)
                raise KaiPricingError("upstream_timeout")
            return self.history_payload(product_id), 1000

        with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
            "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
        ), patch.object(settings, "KAI_CANDLE_TOTAL_TIMEOUT", 0.08):
            value = get_aggregated_candles("RTX4090", "24GB", "7d")

        self.assertEqual(value["provenance"]["selected_product_ids"], ["product-b"])
        self.assertEqual(value["provenance"]["selection_completeness"], "partial_before_deadline")
        self.assertLessEqual(len(_CANDLE_EXECUTOR._threads), _CANDLE_WORKERS)
        time.sleep(0.12)  # let the deliberately slow shared-worker test task finish

    def test_completion_order_cannot_change_deterministic_candidate_aggregate(self):
        rows = [quote("product-a"), quote("product-b"), quote("product-c")]

        def run_with(delays):
            clear_caches()

            def history(product_id, _interval, _months=1, *, deadline=None):
                time.sleep(delays[product_id])
                base = {"product-a": "2.0", "product-b": "2.4", "product-c": "2.8"}[product_id]
                return self.history_payload(product_id, base=base), 1000

            with patch("app.integrations.kai_pricing.fetch_price_batch", return_value=self.batch(rows)), patch(
                "app.integrations.kai_pricing._fetch_product_candles", side_effect=history,
            ), patch.object(settings, "KAI_CANDLE_TOTAL_TIMEOUT", 1):
                return get_aggregated_candles("RTX4090", "24GB", "7d")

        first = run_with({"product-a": 0.04, "product-b": 0.01, "product-c": 0.02})
        second = run_with({"product-a": 0.01, "product-b": 0.04, "product-c": 0.02})

        self.assertEqual(first["provenance"]["selected_product_ids"], ["product-a", "product-b", "product-c"])
        self.assertEqual(first["provenance"]["selected_product_ids"], second["provenance"]["selected_product_ids"])
        self.assertEqual(first["candles"], second["candles"])
        self.assertEqual(first["provenance"]["selection_completeness"], "full")


if __name__ == "__main__":
    unittest.main()
