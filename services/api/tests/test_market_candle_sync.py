import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.market_price import MarketCandleSyncStatus, MarketPriceCandle, MarketPriceSnapshot
from app.services.market_candle_sync import sync_market_candles


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

    def payload(self):
        start = datetime(2026, 8, 20)
        return {
            "gpu_model": "H100",
            "gpu_variant": "80GB",
            "range": "90d",
            "method": "kai_official_ohlc",
            "data_quality": "official_historical_ohlc",
            "provenance": {"data_version": 7, "as_of": "2026-08-22T12:00:00Z"},
            "candles": [{
                "start_time": (start + timedelta(days=day)).isoformat() + "Z",
                "end_time": (start + timedelta(days=day + 1)).isoformat() + "Z",
                "open_price_cny": 25 + day,
                "high_price_cny": 26 + day,
                "low_price_cny": 24 + day,
                "close_price_cny": 25.5 + day,
                "sample_count": 8,
                "observation_count": 8,
                "sources": ["kai"],
            } for day in range(2)],
        }

    def test_agent_persists_official_candles_idempotently(self):
        with patch("app.services.market_candle_sync.SessionLocal", self.session_factory), patch(
            "app.services.market_candle_sync.get_aggregated_candles", return_value=self.payload(),
        ) as fetch:
            first = sync_market_candles(force=True)
            second = sync_market_candles(force=True)

        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["inserted"], 2)
        self.assertEqual(second["inserted"], 0)
        self.assertTrue(all(call.args[2] == "90d" for call in fetch.call_args_list))
        db = self.session_factory()
        self.assertEqual(db.query(MarketPriceCandle).count(), 2)
        status = db.query(MarketCandleSyncStatus).one()
        self.assertEqual(status.status, "ok")
        self.assertEqual(status.candle_count, 2)
        db.close()


if __name__ == "__main__":
    unittest.main()
