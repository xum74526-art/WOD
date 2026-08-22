import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Lock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.market_price import MarketHistoryPoint
from app.routers.market import _MarketResponseCache
from app.services.market_history_sync import select_market_history_bulk


class MarketPerformanceTests(unittest.TestCase):
    def test_duplicate_market_requests_share_one_loader(self):
        cache = _MarketResponseCache(max_entries=8)
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

