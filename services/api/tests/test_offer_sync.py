import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.product import Product
from app.services.offer_sync import _upsert_kai_products, sync_offers


class OfferSyncTests(unittest.TestCase):
    def test_sync_calls_only_kai_provider(self):
        with patch(
            "app.services.offer_sync._sync_kai_products",
            return_value={"status": "live", "upserted": 3},
        ) as kai:
            result = sync_offers()

        kai.assert_called_once_with()
        self.assertEqual(result, {"kai": {"status": "live", "upserted": 3}})

    def test_kai_sync_soft_disables_missing_and_legacy_vast_without_deleting(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Product.__table__.create(engine)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            db.add_all([
                Product(
                    name="Old KAI", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    market_source="kai", external_product_id="old-kai", source_price=Decimal("2"),
                    source_currency="CNY", stock=2, status="on",
                ),
                Product(
                    name="Legacy Vast", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    market_source="vast", external_product_id="old-vast", source_price=Decimal("0.2"),
                    source_currency="USD", stock=2, status="on",
                ),
                Product(
                    name="Legacy AutoDL", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    market_source="autodl", external_product_id="old-autodl", source_price=Decimal("2"),
                    source_currency="CNY", stock=2, status="on",
                ),
            ])
            db.commit()

        current = [{
            "external_product_id": "kai-current", "gpu_model": "RTX4090",
            "gpu_variant": "24GB", "display_name": "RTX 4090 24GB",
            "region": "CN-East", "price_cny": Decimal("2.5"),
            "max_configurable_quantity": 4, "observed_at": datetime(2026, 8, 21, 4),
        }]
        with patch("app.services.offer_sync.SessionLocal", factory):
            self.assertEqual(_upsert_kai_products(current), 1)
            self.assertEqual(_upsert_kai_products(current), 1)

        with factory() as db:
            created = db.query(Product).filter(Product.external_product_id == "kai-current").one()
            self.assertEqual(created.stock, 3)
            self.assertEqual(created.platform_stock_cap, 3)
            self.assertEqual(created.source_max_configurable_quantity, 4)
            self.assertEqual(created.cycle, [])

        # A market refresh updates the source maximum but must not replenish
        # consumed platform test allocation.
        with factory() as db:
            created = db.query(Product).filter(Product.external_product_id == "kai-current").one()
            created.stock = 1
            db.commit()
        current[0]["max_configurable_quantity"] = 6
        with patch("app.services.offer_sync.SessionLocal", factory):
            self.assertEqual(_upsert_kai_products(current), 1)

        with factory() as db:
            self.assertEqual(db.query(Product).count(), 4)
            created = db.query(Product).filter(Product.external_product_id == "kai-current").one()
            self.assertEqual(created.stock, 1)
            self.assertEqual(created.platform_stock_cap, 3)
            self.assertEqual(created.source_max_configurable_quantity, 6)
            self.assertEqual(
                created.stock_semantics,
                "platform_closed_test_manual_fulfillment_allocation",
            )
            self.assertIn("平台人工履约额度", created.desc)
            self.assertIn("不是实时库存", created.desc)
            old_kai = db.query(Product).filter(Product.external_product_id == "old-kai").one()
            old_vast = db.query(Product).filter(Product.external_product_id == "old-vast").one()
            old_autodl = db.query(Product).filter(Product.external_product_id == "old-autodl").one()
            self.assertEqual((old_kai.status, old_kai.stock), ("off", 2))
            self.assertEqual((old_vast.status, old_vast.stock), ("off", 0))
            self.assertEqual((old_autodl.status, old_autodl.stock), ("off", 0))


if __name__ == "__main__":
    unittest.main()
