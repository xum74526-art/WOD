import unittest
from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.vast_market import MarketIngestionBatch, VastOffer, VastPriceSnapshot, VastSyncStatus


TOKEN = "local-test-ingestion-token-32-characters"


def payload(batch_id: str = "vast:on-demand:test-001", offer_id: int = 101, price: float = 0.5) -> dict:
    return {
        "schema_version": "1.0",
        "source": "vast",
        "dataset": "gpu_offers",
        "billing_mode": "on-demand",
        "batch_id": batch_id,
        "sync_mode": "incremental",
        "observed_at": "2026-08-22T12:00:00Z",
        "refresh_seconds": 600,
        "upstream_rate_limit": 5,
        "upstream_rate_limit_remaining": 4,
        "records": [{
            "external_id": offer_id,
            "gpu_name": "RTX 4090",
            "gpu_model": "RTX4090",
            "gpu_variant": "24GB",
            "gpu_count": 1,
            "gpu_ram_mb": 24564,
            "gpu_total_ram_mb": 24564,
            "currency": "USD",
            "compute_price_hourly": price,
            "total_price_hourly": price + 0.01,
            "per_gpu_compute_price_hourly": price,
            "per_gpu_total_price_hourly": price + 0.01,
            "reliability": 0.998,
            "rentable": True,
            "rented": False
        }]
    }


class MarketIngestionApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        for table in (VastOffer, VastPriceSnapshot, VastSyncStatus, MarketIngestionBatch):
            table.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.previous_enabled = settings.MARKET_INGESTION_ENABLED
        self.previous_token = settings.MARKET_INGESTION_TOKEN
        settings.MARKET_INGESTION_ENABLED = True
        settings.MARKET_INGESTION_TOKEN = TOKEN
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_db, None)
        settings.MARKET_INGESTION_ENABLED = self.previous_enabled
        settings.MARKET_INGESTION_TOKEN = self.previous_token

    def post(self, body: dict, token: str = TOKEN):
        return self.client.post(
            "/internal/v1/ingestion/market-offers/batches",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )

    def test_internal_endpoint_requires_service_token(self):
        response = self.client.post(
            "/internal/v1/ingestion/market-offers/batches",
            json=payload(),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 1)

    def test_batch_writes_once_and_duplicate_is_idempotent(self):
        first = self.post(payload())
        second = self.post(payload())
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["data"]["duplicate"])
        self.assertTrue(second.json()["data"]["duplicate"])
        db = self.Session()
        self.assertEqual(db.query(VastOffer).count(), 1)
        self.assertEqual(db.query(VastPriceSnapshot).count(), 1)
        self.assertEqual(db.query(MarketIngestionBatch).count(), 1)
        self.assertEqual(db.get(VastSyncStatus, "on-demand").active_offer_count, 1)
        db.close()

    def test_same_batch_id_with_different_payload_is_rejected(self):
        self.assertEqual(self.post(payload()).status_code, 200)
        changed = deepcopy(payload())
        changed["records"][0]["compute_price_hourly"] = 0.9
        response = self.post(changed)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 40901)

    def test_snapshot_batch_deactivates_missing_offer_only_after_success(self):
        self.assertEqual(self.post(payload("vast:on-demand:snapshot-a", 101)).status_code, 200)
        second = payload("vast:on-demand:snapshot-b", 202)
        second["sync_mode"] = "snapshot"
        second["observed_at"] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.post(second).status_code, 200)
        db = self.Session()
        self.assertFalse(db.query(VastOffer).filter(VastOffer.external_offer_id == 101).one().active)
        self.assertTrue(db.query(VastOffer).filter(VastOffer.external_offer_id == 202).one().active)
        db.close()


if __name__ == "__main__":
    unittest.main()
