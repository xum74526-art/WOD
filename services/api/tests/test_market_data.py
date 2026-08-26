import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Supplier, User
from app.models.market_price import MarketPriceSnapshot, MarketSourceStatus
from app.models.product import Product
from app.utils.response import BizError
from app.services.gpu_catalog import canonicalize_gpu, memory_variant_from_gb, memory_variant_from_text
from app.routers.market import _build_market_candles, _history_metric_matches_live_sources, _public_error_code, _range_volatility, _seven_day_metrics, _source_range_metric, _source_state, _with_card_hour_candles, latest_prices
from app.core.config import settings
from app.routers.product import _current_product_query, _product_out, price_trend, quote_regional
from app.services.market_freshness import product_market_state
from app.services.region_mapper import map_region
from app.services.market_sync import _aggregate_and_store, _percentile, _without_outliers


class MarketDataTests(unittest.TestCase):
    def test_latest_prices_reports_selected_source_refresh_interval(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(engine)
        MarketSourceStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime.now()

        db.add(MarketSourceStatus(
            source="kai", enabled=True, status="ok", refresh_seconds=1,
            sample_count=1, last_attempt_at=now, last_success_at=now,
        ))
        db.add(MarketPriceSnapshot(
            source="kai", gpu_model="RTX4090", gpu_variant="24GB",
            billing_mode="ondemand", currency="CNY",
            min_price=Decimal("2"), p25_price=Decimal("2"),
            median_price=Decimal("2"), p75_price=Decimal("2"), max_price=Decimal("2"),
            min_price_cny=Decimal("2"), median_price_cny=Decimal("2"),
            max_price_cny=Decimal("2"), sample_count=1, available_gpu_count=0,
            signature="refresh-kai", observed_at=now, fetched_at=now,
        ))
        db.commit()

        result = latest_prices("RTX4090", "24GB", "kai", db)["data"]
        self.assertEqual(result["next_refresh_in"], settings.KAI_PRICING_REFRESH_SECONDS)
        self.assertEqual(result["summary"]["quote_sample_count"], 1)
        self.assertIsNone(result["summary"]["inventory_available"])
        self.assertEqual(result["summary"]["wallet_charge_unit"], "CARD_HOUR")
        self.assertAlmostEqual(
            result["summary"]["median_price_card_hours"],
            2 / settings.CARD_HOUR_RMB_RATE,
            places=6,
        )
        for retired in ("autodl", "vast", "wod", "kai,autodl"):
            with self.assertRaises(BizError):
                latest_prices("RTX4090", "24GB", retired, db)
        db.close()

    def test_official_candles_include_wallet_card_hour_values(self):
        payload = _with_card_hour_candles({
            "latest_live_price_cny": 2.004,
            "candles": [{
                "open_price_cny": 1.002,
                "high_price_cny": 2.004,
                "low_price_cny": 0.501,
                "close_price_cny": 1.503,
            }],
        })
        candle = payload["candles"][0]
        self.assertEqual(payload["wallet_charge_unit"], "CARD_HOUR")
        self.assertEqual(payload["card_hour_rmb_rate"], settings.CARD_HOUR_RMB_RATE)
        self.assertEqual(payload["latest_live_price_card_hours"], 2.0)
        self.assertEqual(candle["open_price_card_hours"], 1.0)
        self.assertEqual(candle["high_price_card_hours"], 2.0)
        self.assertEqual(candle["low_price_card_hours"], 0.5)
        self.assertEqual(candle["close_price_card_hours"], 1.5)

    def test_archived_change_requires_the_same_live_provider(self):
        vast_history = {"history_provenance": {"upstream_provider": "vast"}}
        autodl_history = {"history_provenance": {"upstream_provider": "autodl"}}
        self.assertFalse(_history_metric_matches_live_sources(vast_history, ["autodl"]))
        self.assertFalse(_history_metric_matches_live_sources(vast_history, ["wod"]))
        self.assertTrue(_history_metric_matches_live_sources(vast_history, ["vast"]))
        self.assertTrue(_history_metric_matches_live_sources(vast_history, ["autodl", "vast"]))
        self.assertTrue(_history_metric_matches_live_sources(autodl_history, ["autodl"]))

    def test_legacy_text_reliability_never_breaks_product_catalogue(self):
        product = Product(
            id=1,
            name="RTX 4090",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("1.50"),
            status="on",
            stock=1,
        )
        product.reliability = "-"
        output = _product_out(product, source_states={})
        self.assertIsNone(output["stability"])

    def test_kai_product_output_neutralizes_legacy_rollout_description(self):
        product = Product(
            id=2,
            name="RTX 4090",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("2.50"),
            status="on",
            stock=1,
            market_source="kai",
            desc="KAI Pricing 当前卡时报价；数量为平台封闭测试人工履约额度",
        )
        output = _product_out(product, source_states={})
        self.assertIn("平台按已确认的履约额度协调交付", output["desc"])
        self.assertNotIn("不是实时库存", output["desc"])
        self.assertNotIn("封闭测试", output["desc"])
        self.assertNotIn("closed_test", output["desc"].lower())
        self.assertEqual(
            output["stock_semantics"],
            "platform_manual_fulfillment_allocation",
        )
        self.assertNotIn("closed_test", output["stock_semantics"].lower())

    def test_gpu_names_are_normalized_without_merging_distinct_models(self):
        self.assertEqual(canonicalize_gpu("NVIDIA GeForce RTX 4090"), "RTX4090")
        self.assertEqual(canonicalize_gpu("RTX 4090D"), "RTX4090D")
        self.assertEqual(canonicalize_gpu("A100-PCIE-40GB"), "A100")
        self.assertEqual(canonicalize_gpu("RTX PRO 6000 WS"), "RTXPRO6000")
        self.assertEqual(canonicalize_gpu("rtx3080Ti"), "RTX3080TI")
        self.assertEqual(canonicalize_gpu("vGPU32"), "VGPU32")

    def test_memory_units_are_normalized_to_gpu_variants(self):
        self.assertEqual(memory_variant_from_gb(31.84), "32GB")
        self.assertEqual(memory_variant_from_text("80 GB HBM3"), "80GB")
        self.assertEqual(memory_variant_from_text("unknown"), "")

    def test_kai_compact_region_codes_are_mapped_without_composition_bias(self):
        self.assertEqual(map_region("CN-East"), ("east_china", "华东"))
        self.assertEqual(map_region("CN-Northeast"), ("northeast_china", "东北"))
        self.assertEqual(map_region("US-West"), ("north_america", "北美"))
        self.assertEqual(map_region("EU-Central"), ("europe", "欧洲"))

    def test_market_percentiles_use_observed_values(self):
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        self.assertEqual(_percentile(values, Decimal("0.5")), Decimal("2.5"))
        self.assertEqual(_percentile(values, Decimal("0.25")), Decimal("1.75"))

    def test_market_candles_use_real_ohlc_without_filling_missing_buckets(self):
        start = datetime(2026, 8, 18, 8, 0)

        def row(minute: int, price: str, source: str = "vast", samples: int = 1):
            return SimpleNamespace(
                observed_at=start + timedelta(minutes=minute),
                median_price_cny=Decimal(price),
                sample_count=samples,
                source=source,
            )

        candles = _build_market_candles([
            row(0, "10", "vast", 3),
            row(1, "12", "autodl", 1),
            row(5, "11"),
            row(9, "13"),
            # Deliberately leave the 08:10 candle empty.
            row(16, "9"),
        ], candle_seconds=5 * 60, tick_seconds=60)

        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[0]["open_price_cny"], 10.0)
        self.assertEqual(candles[0]["high_price_cny"], 12.0)
        self.assertEqual(candles[0]["low_price_cny"], 10.0)
        self.assertEqual(candles[0]["close_price_cny"], 12.0)
        self.assertEqual(candles[0]["sources"], ["autodl", "vast"])
        self.assertTrue(candles[2]["start_time"].startswith("2026-08-18T08:15"))

    def test_market_candle_tick_uses_sample_weighted_observed_median(self):
        observed_at = datetime(2026, 8, 18, 8, 1)
        rows = [
            SimpleNamespace(observed_at=observed_at, median_price_cny=Decimal("1"), sample_count=10, source="vast"),
            SimpleNamespace(observed_at=observed_at, median_price_cny=Decimal("9"), sample_count=1, source="autodl"),
        ]
        candles = _build_market_candles(rows, candle_seconds=5 * 60, tick_seconds=60)
        self.assertEqual(candles[0]["open_price_cny"], 1.0)
        self.assertEqual(candles[0]["close_price_cny"], 1.0)

    def test_market_candles_do_not_mix_seller_price_range_into_time_ohlc(self):
        observed_at = datetime(2026, 8, 18, 8, 1)
        rows = [
            SimpleNamespace(
                observed_at=observed_at,
                median_price_cny=Decimal("2.20"),
                min_price_cny=Decimal("1.80"),
                max_price_cny=Decimal("2.70"),
                sample_count=8,
                source="vast",
            ),
            SimpleNamespace(
                observed_at=observed_at + timedelta(minutes=1),
                median_price_cny=Decimal("2.25"),
                min_price_cny=Decimal("1.75"),
                max_price_cny=Decimal("2.85"),
                sample_count=7,
                source="vast",
            ),
        ]
        candles = _build_market_candles(rows, candle_seconds=5 * 60, tick_seconds=60)
        self.assertEqual(candles[0]["open_price_cny"], 2.20)
        self.assertEqual(candles[0]["close_price_cny"], 2.25)
        self.assertEqual(candles[0]["low_price_cny"], 2.20)
        self.assertEqual(candles[0]["high_price_cny"], 2.25)

    def test_daily_market_candles_preserve_real_red_green_ohlc(self):
        start = datetime(2026, 8, 12, 6, 0)

        def row(hours: int, price: str):
            return SimpleNamespace(
                observed_at=start + timedelta(hours=hours),
                median_price_cny=Decimal(price),
                sample_count=1,
                source="hf_gpu_prices",
            )

        candles = _build_market_candles([
            row(0, "2.44"),
            row(12, "2.46"),
            row(24, "2.45"),
            row(36, "2.43"),
        ], candle_seconds=24 * 60 * 60, tick_seconds=60 * 60)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["open_price_cny"], 2.44)
        self.assertEqual(candles[0]["close_price_cny"], 2.46)
        self.assertEqual(candles[0]["high_price_cny"], 2.46)
        self.assertEqual(candles[0]["low_price_cny"], 2.44)
        self.assertEqual(candles[1]["open_price_cny"], 2.45)
        self.assertEqual(candles[1]["close_price_cny"], 2.43)

    def test_extreme_offer_is_excluded_from_default_aggregate(self):
        values = [Decimal("1.0"), Decimal("1.1"), Decimal("1.2"), Decimal("50")]
        self.assertEqual(_without_outliers(values), values[:3])

    def test_snapshot_aggregate_uses_robust_median_per_exact_contract(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        observed_at = datetime(2026, 8, 10, 0, 0)

        def offer(model: str, billing_mode: str, price: str):
            return {
                "gpu_model": model,
                "gpu_variant": "24GB",
                "billing_mode": billing_mode,
                "currency": "CNY",
                "price": Decimal(price),
                "available": 1,
            }

        rows = [offer("RTX4090", "ondemand", price) for price in ("1.0", "1.1", "1.2", "50")]
        rows += [offer("RTX4090", "reserved", price) for price in ("10", "11")]
        rows += [offer("RTX3090", "ondemand", "20")]
        inserted, _ = _aggregate_and_store(db, "kai", rows, observed_at)
        db.commit()

        self.assertEqual(inserted, 3)
        snapshots = {
            (row.gpu_model, row.billing_mode): row
            for row in db.query(MarketPriceSnapshot).all()
        }
        self.assertEqual(snapshots[("RTX4090", "ondemand")].sample_count, 3)
        self.assertEqual(snapshots[("RTX4090", "ondemand")].median_price_cny, Decimal("1.100000"))
        self.assertEqual(snapshots[("RTX4090", "reserved")].median_price_cny, Decimal("10.500000"))
        self.assertEqual(snapshots[("RTX3090", "ondemand")].median_price_cny, Decimal("20.000000"))
        db.close()

    def test_retired_provider_cannot_write_new_market_snapshots(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        with self.assertRaises(ValueError):
            _aggregate_and_store(db, "autodl", [], datetime(2026, 8, 21))
        self.assertEqual(db.query(MarketPriceSnapshot).count(), 0)
        db.close()

    def test_range_volatility_uses_observed_prices(self):
        self.assertEqual(_range_volatility([Decimal("100"), Decimal("110")]), 9.52)
        self.assertEqual(_range_volatility([Decimal("100")]), 0.0)

    def test_intraday_range_is_not_mislabeled_as_seven_day_history(self):
        start = datetime(2026, 8, 15, 4, 0)
        metric = _source_range_metric([
            (start, Decimal("0.661646")),
            (start + timedelta(hours=8), Decimal("1.695412")),
        ])
        self.assertIsNone(metric["volatility_7d"])
        self.assertEqual(metric["volatility_status"], "insufficient_history")
        self.assertEqual(metric["history_day_count"], 1)

    def test_real_sparse_endpoints_spanning_week_are_available_but_limited(self):
        start = datetime(2026, 8, 11, 4, 0)
        metric = _source_range_metric([
            (start, Decimal("1.00")),
            (start + timedelta(days=2), Decimal("1.02")),
            (start + timedelta(days=4), Decimal("1.04")),
            (start + timedelta(days=6), Decimal("1.06")),
        ])
        self.assertEqual(metric["volatility_status"], "available")
        self.assertEqual(metric["volatility_quality"], "limited_sample")
        self.assertEqual(metric["history_coverage_status"], "sparse_window")
        self.assertEqual(metric["change_7d_pct"], 6.0)
        self.assertEqual(metric["range_low_cny"], 1.0)
        self.assertEqual(metric["range_high_cny"], 1.06)

    def test_h200_capacity_aliases_form_one_temporal_series(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 11, 4, 0)
        for day in range(7):
            value = Decimal("2") + Decimal(day) / Decimal("100")
            variant = "140GB" if day < 3 else "141GB"
            db.add(MarketPriceSnapshot(
                source="vast", gpu_model="H200", gpu_variant=variant, billing_mode="ondemand", currency="USD",
                min_price=value, p25_price=value, median_price=value, p75_price=value, max_price=value,
                min_price_cny=value, median_price_cny=value, max_price_cny=value, sample_count=2,
                available_gpu_count=2, fx_rate=Decimal("1"), fx_source="test", fx_date="2026-08-18",
                data_quality="verified", signature=f"h200-{day}", observed_at=start + timedelta(days=day),
                fetched_at=start + timedelta(days=day),
            ))
        db.commit()
        metrics = _seven_day_metrics(db, start + timedelta(days=7), {"vast"})
        self.assertIn(("H200", "141GB"), metrics)
        self.assertNotIn(("H200", "140GB"), metrics)
        self.assertEqual(metrics[("H200", "141GB")]["history_day_count"], 7)
        self.assertEqual(metrics[("H200", "141GB")]["change_7d_pct"], 3.0)
        db.close()

    def test_daily_medians_filter_intraday_outlier_after_full_coverage(self):
        start = datetime(2026, 8, 10, 1, 0)
        points = [
            (start, Decimal("100")),
            (start + timedelta(hours=1), Decimal("101")),
            (start + timedelta(hours=2), Decimal("102")),
            (start + timedelta(hours=3), Decimal("500")),
        ]
        for day in range(1, 7):
            center = Decimal(101 + day)
            points.extend([
                (start + timedelta(days=day), center - 1),
                (start + timedelta(days=day, hours=1), center),
                (start + timedelta(days=day, hours=2), center + 1),
            ])
        metric = _source_range_metric(points)
        self.assertEqual(metric["volatility_7d"], 5.77)
        self.assertEqual(metric["volatility_status"], "available")
        self.assertEqual(metric["volatility_quality"], "verified")
        self.assertEqual(metric["history_day_count"], 7)

    def test_event_driven_snapshot_churn_does_not_weight_daily_representative(self):
        start = datetime(2026, 8, 10, 0, 0)
        points = []
        for day in range(7):
            # Opposite event counts on alternating days would create a large
            # false move if raw snapshots were treated as equally spaced time.
            low_repeats, high_repeats = ((100, 1) if day % 2 == 0 else (1, 100))
            points.extend((start + timedelta(days=day, seconds=i), Decimal("100")) for i in range(low_repeats))
            points.extend((start + timedelta(days=day, hours=1, seconds=i), Decimal("120")) for i in range(high_repeats))
        metric = _source_range_metric(points)
        self.assertEqual(metric["volatility_7d"], 0.0)
        self.assertEqual(metric["history_day_count"], 7)
        self.assertEqual(metric["history_bucket_count"], 14)

    def test_source_freshness_rejects_stale_and_unavailable_snapshots(self):
        now = datetime(2026, 8, 17, 8, 0)
        live = SimpleNamespace(status="ok", last_success_at=now - timedelta(seconds=20), refresh_seconds=30)
        recent_failure = SimpleNamespace(status="error", last_success_at=now - timedelta(seconds=20), refresh_seconds=30)
        stale = SimpleNamespace(status="ok", last_success_at=now - timedelta(minutes=4), refresh_seconds=30)
        unavailable = SimpleNamespace(status="error", last_success_at=now - timedelta(hours=2), refresh_seconds=30)
        self.assertEqual(_source_state(live, now), "live")
        self.assertEqual(_source_state(recent_failure, now), "delayed")
        self.assertEqual(_source_state(stale, now), "stale")
        self.assertEqual(_source_state(unavailable, now), "unavailable")

    def test_source_errors_are_exposed_only_as_sanitized_codes(self):
        self.assertEqual(_public_error_code("missing provider credential"), "credentials_missing")
        self.assertEqual(_public_error_code("401 Unauthorized"), "authentication_failed")
        self.assertEqual(_public_error_code("authentication_failed"), "authentication_failed")
        self.assertEqual(_public_error_code("429 rate limit"), "rate_limited")
        self.assertEqual(_public_error_code("secret provider detail"), "upstream_error")

    def test_external_product_expires_even_when_provider_is_live(self):
        now = datetime(2026, 8, 17, 8, 0)
        current = SimpleNamespace(
            source_price=Decimal("1"), source_currency="USD",
            price_updated_at=now - timedelta(minutes=5),
        )
        expired = SimpleNamespace(
            source_price=Decimal("1"), source_currency="USD",
            price_updated_at=now - timedelta(minutes=20),
        )
        self.assertEqual(product_market_state(current, {"vast": "live"}, now, 900), "live")
        self.assertEqual(product_market_state(expired, {"vast": "live"}, now, 900), "stale")
        self.assertEqual(product_market_state(current, {"vast": "unavailable"}, now, 900), "unavailable")

    def test_kai_and_first_party_wod_remain_visible_while_retired_sources_are_hidden(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        observed_at = datetime.now() - timedelta(minutes=1)
        merchant_user = User(
            username="行情测试商家",
            phone="13900009001",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        db.add(merchant_user)
        db.flush()
        merchant = Supplier(
            user_id=merchant_user.id,
            company_name="行情测试商家",
            contact="联系人",
            phone=merchant_user.phone,
            status="approved",
        )
        db.add(merchant)
        db.flush()

        def product(name: str, source: str, currency: str | None):
            return Product(
                name=name,
                gpu_model="RTX4090",
                memory="24GB",
                price=Decimal("1.5"),
                source_price=Decimal("1") if currency else None,
                source_currency=currency,
                market_source=source,
                price_updated_at=observed_at if currency else None,
                stock=2,
                reliability=99,
                status="on",
            )

        db.add_all([
            product("KAI offer", "kai", "CNY"),
            product("Vast offer", "vast", "USD"),
            product("AutoDL offer", "autodl", "CNY"),
            product("WOD listing", "wod", None),
        ])
        wod_listing = db.query(Product).filter(Product.name == "WOD listing").one()
        wod_listing.supplier_id = merchant.id
        db.commit()

        delayed = _current_product_query(db, {"kai": "delayed"}).all()
        self.assertEqual({item.name for item in delayed}, {"KAI offer", "WOD listing"})
        unavailable = _current_product_query(db, {"kai": "unavailable"}).all()
        self.assertEqual([item.name for item in unavailable], ["WOD listing"])
        db.close()

    def test_regional_quote_compares_one_exact_kai_identity_only(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Product.__table__.create(engine)
        MarketSourceStatus.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        now = datetime.now()
        db.add(MarketSourceStatus(
            source="kai", enabled=True, status="ok", refresh_seconds=30,
            sample_count=4, last_attempt_at=now, last_success_at=now,
        ))

        def product(model: str, memory: str, city: str, price: str, external_id: str):
            return Product(
                name=f"{model} {memory} {city}", gpu_model=model, memory=memory,
                price=Decimal(price), source_price=Decimal(price), source_currency="CNY",
                market_source="kai", external_product_id=external_id, city=city,
                price_updated_at=now, stock=1, reliability=99, status="on",
            )

        db.add_all([
            product("RTX4090", "24GB", "中国大陆-华北", "2.00", "north-a"),
            product("RTX4090", "24GB", "中国大陆-华北", "2.20", "north-b"),
            product("RTX4090", "24GB", "中国大陆-华东", "3.00", "east-a"),
            # Must not distort the overseas comparison for RTX4090.
            product("H200", "141GB", "欧洲", "25.00", "europe-h200"),
        ])
        db.commit()

        data = quote_regional("RTX 4090", "24 GB", db)["data"]
        self.assertEqual((data["gpu_model"], data["gpu_variant"]), ("RTX4090", "24GB"))
        self.assertEqual(data["source"], "kai")
        self.assertEqual(data["region_count"], 2)
        self.assertEqual({item["region"] for item in data["regions"]}, {"华北", "华东"})
        north = next(item for item in data["regions"] if item["region"] == "华北")
        east = next(item for item in data["regions"] if item["region"] == "华东")
        self.assertEqual(north["median_price_cny"], 2.1)
        self.assertEqual(north["quote_sample_count"], 2)
        self.assertEqual(east["relative_to_lowest_pct"], 42.86)
        self.assertEqual(data["sample_semantics"], "current_quote_observations_not_inventory")
        db.close()

    def test_seven_day_metric_keeps_billing_modes_separate(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        start = datetime(2026, 8, 10, 1, 0)

        def snapshot(billing_mode: str, price: str, observed_at: datetime, suffix: str):
            value = Decimal(price)
            return MarketPriceSnapshot(
                source="vast",
                gpu_model="RTX4090",
                gpu_variant="24GB",
                billing_mode=billing_mode,
                currency="CNY",
                min_price=value,
                p25_price=value,
                median_price=value,
                p75_price=value,
                max_price=value,
                min_price_cny=value,
                median_price_cny=value,
                max_price_cny=value,
                sample_count=5,
                available_gpu_count=5,
                fx_rate=Decimal("1"),
                fx_source="test",
                fx_date="2026-08-10",
                data_quality="verified",
                signature=f"sig-{suffix}",
                observed_at=observed_at,
                fetched_at=observed_at,
            )

        rows = []
        for day in range(7):
            rows.append(snapshot("ondemand", str(Decimal("1.0") + Decimal(day) / 100), start + timedelta(days=day), f"o-{day}"))
            rows.append(snapshot("reserved", str(Decimal("10.0") - Decimal(day) / 100), start + timedelta(days=day), f"r-{day}"))
        db.add_all(rows)
        db.commit()
        metric = _seven_day_metrics(db, datetime(2026, 8, 16, 1), {"vast"})[("RTX4090", "24GB")]
        self.assertAlmostEqual(metric["volatility_7d"], 5.83, places=2)
        self.assertEqual(metric["volatility_billing_mode"], "ondemand")
        self.assertEqual(metric["volatility_source_count"], 1)
        self.assertEqual(metric["history_day_count"], 7)
        db.close()

    def test_unchanged_price_is_periodically_persisted_as_real_observation(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        row = {
            "gpu_model": "RTX4090",
            "gpu_variant": "24GB",
            "billing_mode": "ondemand",
            "currency": "CNY",
            "price": Decimal("1.25"),
            "available": 2,
        }
        start = datetime(2026, 8, 10, 0, 0)

        self.assertEqual(_aggregate_and_store(db, "kai", [row], start)[0], 1)
        db.commit()
        self.assertEqual(_aggregate_and_store(db, "kai", [row], start + timedelta(minutes=30))[0], 0)
        db.commit()
        self.assertEqual(_aggregate_and_store(db, "kai", [row], start + timedelta(hours=1))[0], 1)
        db.commit()
        self.assertEqual(db.query(MarketPriceSnapshot).count(), 2)
        db.close()

    def test_product_trend_does_not_join_different_sources(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Product.__table__.create(engine)
        MarketPriceSnapshot.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        product = Product(
            name="RTX 4090", gpu_model="RTX4090", memory="24GB",
            price=Decimal("7"), source_price=Decimal("1"), source_currency="USD",
            exchange_rate=Decimal("7"), stock=1, reliability=99, status="on",
        )
        db.add(product)
        db.flush()
        observed_at = datetime.now() - timedelta(hours=1)

        def snapshot(source: str, price: str, signature: str):
            value = Decimal(price)
            return MarketPriceSnapshot(
                source=source, gpu_model="RTX4090", gpu_variant="24GB",
                billing_mode="ondemand", currency="CNY",
                min_price=value, p25_price=value, median_price=value,
                p75_price=value, max_price=value,
                min_price_cny=value, median_price_cny=value, max_price_cny=value,
                sample_count=1, available_gpu_count=1, fx_rate=Decimal("1"),
                fx_source="test", fx_date="2026-08-17", data_quality="limited_sample",
                signature=signature, observed_at=observed_at, fetched_at=observed_at,
            )

        db.add_all([snapshot("vast", "7", "vast-sig"), snapshot("autodl", "1", "autodl-sig")])
        db.commit()
        points = price_trend(product.id, db)["data"]
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["source"], "vast")
        self.assertEqual(points[0]["billing_mode"], "ondemand")
        db.close()


if __name__ == "__main__":
    unittest.main()
