import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import MarketSourceStatus, Product  # noqa: F401
from app.routers.product import list_products


class ProductCatalogTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        now = datetime.now()
        self.db.add(MarketSourceStatus(
            source="kai",
            enabled=True,
            status="ok",
            refresh_seconds=300,
            sample_count=4,
            last_attempt_at=now,
            last_success_at=now,
        ))
        self.db.add_all([
            self._product("kai-a10-expensive", "A10", "24GB", "3.00", now),
            self._product("kai-a10-lowest", "A10", "24GB", "2.00", now),
            self._product("kai-a100-40", "A100", "40GB", "4.00", now),
            self._product("kai-a100-80", "A100", "80GB", "5.00", now),
            Product(
                name="WOD A40",
                gpu_model="A40",
                memory="48GB",
                price=Decimal("1.00"),
                cycle=[30],
                stock=1,
                status="on",
                market_source="wod",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def _product(external_id: str, model: str, memory: str, price: str, observed_at: datetime) -> Product:
        return Product(
            name=f"KAI {model} {memory}",
            gpu_model=model,
            memory=memory,
            price=Decimal(price),
            cycle=[],
            stock=10,
            status="on",
            market_source="kai",
            external_product_id=external_id,
            source_price=Decimal(price),
            source_currency="CNY",
            price_updated_at=observed_at,
            source_max_configurable_quantity=10,
            platform_stock_cap=10,
        )

    def _list(self, *, page: int = 1, page_size: int = 100, sort: str = "default"):
        return list_products(
            keyword=None,
            memory=None,
            region=None,
            category=None,
            sort=sort,
            min_price=None,
            max_price=None,
            market_source="kai",
            representative=True,
            page=page,
            page_size=page_size,
            db=self.db,
        )["data"]

    def test_representative_catalog_deduplicates_after_the_full_query(self):
        data = self._list()

        self.assertEqual(data["total"], 3)
        self.assertEqual(
            {(item["gpu_model"], item["memory"]) for item in data["items"]},
            {("A10", "24GB"), ("A100", "40GB"), ("A100", "80GB")},
        )
        a10 = next(item for item in data["items"] if item["gpu_model"] == "A10")
        self.assertEqual(a10["external_product_id"], "kai-a10-lowest")

    def test_representative_catalog_paginates_the_unique_result(self):
        first = self._list(page=1, page_size=2, sort="price_asc")
        second = self._list(page=2, page_size=2, sort="price_asc")

        self.assertEqual(first["total"], 3)
        self.assertEqual([item["gpu_model"] for item in first["items"]], ["A10", "A100"])
        self.assertEqual([item["memory"] for item in first["items"]], ["24GB", "40GB"])
        self.assertEqual([(item["gpu_model"], item["memory"]) for item in second["items"]], [("A100", "80GB")])


if __name__ == "__main__":
    unittest.main()
