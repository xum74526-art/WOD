import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models.market_price import MarketPriceSnapshot, MarketSourceStatus
from app.models.product import Product
from init_db import _ensure_columns, _migrate_product_market_sources


class ProductMarketSourceMigrationTests(unittest.TestCase):
    def test_legacy_table_gains_matching_columns_and_index_on_two_runs(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE products ("
                "id INTEGER PRIMARY KEY, name TEXT, gpu_model TEXT, memory TEXT, price NUMERIC, "
                "source_price NUMERIC, source_currency TEXT, stock INTEGER, status TEXT)"
            ))
            conn.execute(text(
                "INSERT INTO products "
                "(id, name, gpu_model, memory, price, source_price, source_currency, stock, status) "
                "VALUES (1, 'Legacy Vast', 'RTX4090', '24GB', 2, 0.2, 'USD', 5, 'on')"
            ))
        _ensure_columns(engine)
        _migrate_product_market_sources(engine)
        with engine.connect() as conn:
            first_version = conn.execute(text(
                "SELECT version FROM products WHERE id = 1"
            )).scalar_one()
        _ensure_columns(engine)
        _migrate_product_market_sources(engine)

        columns = {item["name"] for item in inspect(engine).get_columns("products")}
        self.assertTrue({
            "market_source",
            "external_product_id",
            "stock_semantics",
            "source_max_configurable_quantity",
            "platform_stock_cap",
            "version",
        }.issubset(columns))
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT market_source, stock_semantics, status, stock, version FROM products WHERE id = 1"
            )).one()
        self.assertEqual(tuple(row[:4]), ("vast", "reported_available_units", "off", 0))
        self.assertGreater(first_version, 1)
        self.assertEqual(row.version, first_version)
        indexes = {item["name"] for item in inspect(engine).get_indexes("products")}
        self.assertIn("ix_products_market_external", indexes)

    def test_migration_is_idempotent_and_soft_disables_vast(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([
                Product(
                    name="WOD", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    source_price=None, source_currency=None, stock=2, status="on",
                    market_source="", stock_semantics=None,
                ),
                Product(
                    name="Legacy Vast", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    source_price=Decimal("0.3"), source_currency="USD", stock=5, status="on",
                    market_source="", stock_semantics=None,
                ),
                Product(
                    name="Legacy KAI", gpu_model="RTX4090", memory="24GB", price=Decimal("2"),
                    source_price=Decimal("2"), source_currency="CNY", stock=5, status="on",
                    market_source="kai", stock_semantics=None,
                    source_max_configurable_quantity=None, platform_stock_cap=None,
                ),
            ])
            db.add(MarketSourceStatus(source="vast", enabled=True, status="ok", refresh_seconds=30))
            db.add(MarketPriceSnapshot(
                source="vast", gpu_model="RTX4090", gpu_variant="24GB", billing_mode="ondemand",
                currency="USD", min_price=Decimal("0.3"), p25_price=Decimal("0.3"),
                median_price=Decimal("0.3"), p75_price=Decimal("0.3"), max_price=Decimal("0.3"),
                sample_count=1, available_gpu_count=5, signature="legacy-vast",
                observed_at=datetime(2026, 8, 20),
            ))
            db.commit()

        with patch.object(settings, "KAI_CLOSED_TEST_INITIAL_STOCK", 3):
            _migrate_product_market_sources(engine)
            # Simulate one fulfilled reservation between startup migrations.
            # Re-running init_db may clamp a value above the platform cap, but
            # must never replenish a consumed closed-test allocation.
            with engine.begin() as conn:
                conn.execute(text("UPDATE products SET stock = 1 WHERE market_source = 'kai'"))
            _migrate_product_market_sources(engine)

        with Session(engine) as db:
            wod, vast, kai = db.query(Product).order_by(Product.id.asc()).all()
            self.assertEqual(wod.market_source, "wod")
            self.assertEqual(wod.stock_semantics, "supplier_reported_inventory")
            self.assertEqual(vast.market_source, "vast")
            self.assertEqual(vast.status, "off")
            self.assertEqual(vast.stock, 0)
            self.assertEqual(kai.market_source, "kai")
            self.assertEqual(
                kai.stock_semantics,
                "platform_closed_test_manual_fulfillment_allocation",
            )
            self.assertEqual(kai.source_max_configurable_quantity, 5)
            self.assertEqual(kai.platform_stock_cap, 3)
            self.assertEqual(kai.stock, 1)
            self.assertEqual(db.query(MarketPriceSnapshot).count(), 1)
            state = db.get(MarketSourceStatus, "vast")
            self.assertFalse(state.enabled)
            self.assertEqual(state.status, "disabled")
        indexes = {item["name"] for item in inspect(engine).get_indexes("products")}
        self.assertIn("ix_products_market_external", indexes)

    def test_duplicate_market_identity_stops_safely_before_unique_index(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE products ("
                "id INTEGER PRIMARY KEY, name TEXT, gpu_model TEXT, memory TEXT, price NUMERIC, "
                "source_price NUMERIC, source_currency TEXT, stock INTEGER, status TEXT)"
            ))
        _ensure_columns(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO products "
                "(id, name, gpu_model, memory, price, source_price, source_currency, stock, status, "
                "market_source, external_product_id) VALUES "
                "(1, 'KAI A', 'RTX4090', '24GB', 2, 2, 'CNY', 3, 'on', 'kai', 'same-id'), "
                "(2, 'KAI B', 'RTX4090', '24GB', 2, 2, 'CNY', 3, 'on', 'kai', 'same-id')"
            ))

        with self.assertRaisesRegex(RuntimeError, "duplicate product market identities"):
            _migrate_product_market_sources(engine)

        indexes = {item["name"] for item in inspect(engine).get_indexes("products")}
        self.assertNotIn("ix_products_market_external", indexes)
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT status, stock_semantics FROM products ORDER BY id"
            )).all()
        self.assertEqual(rows, [("on", None), ("on", None)])


if __name__ == "__main__":
    unittest.main()
