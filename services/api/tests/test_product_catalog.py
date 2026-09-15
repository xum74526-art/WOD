import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.core.config import settings
from app.models import MarketSourceStatus, Product, Supplier, User  # noqa: F401
from app.routers.product import get_product, list_products
from app.utils.response import BizError


class ProductCatalogTests(unittest.TestCase):
    def setUp(self):
        self.original_direct_trade = settings.DIRECT_TRADE_ENABLED
        self.original_matchmaking = settings.MATCHMAKING_ENABLED
        settings.DIRECT_TRADE_ENABLED = True
        settings.MATCHMAKING_ENABLED = True
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
        merchant_users = [
            User(
                username=f"目录商家{i}",
                phone=f"1390000300{i}",
                password="!",
                role="supplier",
                supplier_status="approved",
            )
            for i in (1, 2)
        ]
        self.db.add_all(merchant_users)
        self.db.flush()
        merchants = [
            Supplier(
                user_id=user.id,
                company_name=f"目录商家{i}",
                contact=f"联系人{i}",
                phone=user.phone,
                status="approved",
                rating=4.8 + i / 10,
                order_count=i,
            )
            for i, user in enumerate(merchant_users, start=1)
        ]
        self.db.add_all(merchants)
        self.db.flush()
        self.db.add_all([
            self._product("kai-a10-expensive", "A10", "24GB", "3.00", now),
            self._product("kai-a10-lowest", "A10", "24GB", "2.00", now),
            self._product("kai-a100-40", "A100", "40GB", "4.00", now),
            self._product("kai-a100-80", "A100", "80GB", "5.00", now),
            Product(
                name="ZTW A40",
                gpu_model="A40",
                memory="48GB",
                price=Decimal("1.00"),
                cycle=[30],
                stock=1,
                status="on",
                market_source="wod",
            ),
            Product(
                name="商家 A40 甲",
                gpu_model="A40",
                memory="48GB",
                price=Decimal("1.20"),
                cycle=[30],
                stock=2,
                status="on",
                market_source="wod",
                supplier_id=merchants[0].id,
                stock_semantics="supplier_reported_inventory",
            ),
            Product(
                name="商家 A40 乙",
                gpu_model="A40",
                memory="48GB",
                price=Decimal("1.10"),
                cycle=[30],
                stock=3,
                status="on",
                market_source="wod",
                supplier_id=merchants[1].id,
                stock_semantics="supplier_reported_inventory",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        settings.DIRECT_TRADE_ENABLED = self.original_direct_trade
        settings.MATCHMAKING_ENABLED = self.original_matchmaking
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
        self.assertEqual(a10["seller_type"], "kai_self_operated")
        self.assertEqual(a10["seller_name"], "KAI 自营")
        self.assertEqual(a10["fulfillment_mode"], "platform_manual")
        self.assertEqual(a10["resource_claim_source"], "kai_published")
        self.assertEqual(a10["assurance_label"], "KAI 自营 · 平台人工交付")
        self.assertIn("商品由 KAI 发布", a10["assurance_description"])
        self.assertIn("平台安排人工交付", a10["assurance_description"])
        self.assertIsNone(a10["supplier_id"])
        self.assertIsNone(a10["supplier_name"])

    def test_representative_catalog_resolves_platform_fulfillers_once(self):
        with patch(
            "app.routers.product.configured_platform_fulfiller_ids",
            return_value={1},
        ) as resolve_fulfillers:
            data = self._list()

        self.assertEqual(data["total"], 3)
        resolve_fulfillers.assert_called_once_with(self.db)

    def test_inquiry_mode_never_exposes_a_purchasable_product(self):
        settings.DIRECT_TRADE_ENABLED = False

        items = self._list()["items"]

        self.assertTrue(items)
        self.assertTrue(all(item["interaction_mode"] == "matchmaking" for item in items))
        self.assertTrue(all(item["inquiry_available"] for item in items))
        self.assertTrue(all(not item["purchasable"] for item in items))
        self.assertTrue(all(
            item["purchase_unavailable_reason"] == "当前仅支持提交需求并人工确认"
            for item in items
        ))

    def test_representative_catalog_paginates_the_unique_result(self):
        first = self._list(page=1, page_size=2, sort="price_asc")
        second = self._list(page=2, page_size=2, sort="price_asc")

        self.assertEqual(first["total"], 3)
        self.assertEqual([item["gpu_model"] for item in first["items"]], ["A10", "A100"])
        self.assertEqual([item["memory"] for item in first["items"]], ["24GB", "40GB"])
        self.assertEqual([(item["gpu_model"], item["memory"]) for item in second["items"]], [("A100", "80GB")])

    def test_merchant_catalog_keeps_each_sellers_listing_and_exposes_honest_provider_facts(self):
        data = list_products(
            keyword=None,
            memory=None,
            region=None,
            category=None,
            sort="price_asc",
            min_price=None,
            max_price=None,
            market_source="wod",
            representative=True,
            page=1,
            page_size=100,
            db=self.db,
        )["data"]

        self.assertEqual(data["total"], 2)
        self.assertEqual([item["name"] for item in data["items"]], ["商家 A40 乙", "商家 A40 甲"])
        for item in data["items"]:
            self.assertTrue(item["purchasable"])
            self.assertEqual(item["seller_type"], "merchant")
            self.assertEqual(item["fulfillment_mode"], "merchant_manual")
            self.assertEqual(item["resource_claim_source"], "merchant_declared")
            self.assertEqual(item["purchase_unit"], "hour")
            self.assertEqual(item["min_purchase_hours"], 1)
            self.assertEqual(item["max_purchase_hours"], 720)
            self.assertEqual(item["assurance_label"], "商家身份已审核 · 商家人工交付")
            self.assertIn("平台已审核商家入驻身份", item["assurance_description"])
            self.assertIn("配置与库存由商家自行申报", item["assurance_description"])
            self.assertIn("平台未对商家硬件进行审计或认证", item["assurance_description"])
            self.assertIn("买家确认交付后资金才向商家结算", item["assurance_description"])
            self.assertIn("发起争议", item["assurance_description"])
            self.assertIsNotNone(item["supplier_id"])
            self.assertIsNotNone(item["supplier_name"])
            self.assertIsNotNone(item["supplier_rating"])
            self.assertIsNotNone(item["supplier_order_count"])

    def test_unowned_wod_listing_is_not_exposed_in_public_catalog(self):
        data = list_products(
            keyword=None,
            memory=None,
            region=None,
            category=None,
            sort="default",
            min_price=None,
            max_price=None,
            market_source="wod",
            representative=False,
            page=1,
            page_size=100,
            db=self.db,
        )["data"]

        self.assertNotIn("ZTW A40", {item["name"] for item in data["items"]})

    def test_wod_filter_includes_approved_legacy_untyped_merchant_listing(self):
        supplier = self.db.query(Supplier).filter(
            Supplier.company_name == "目录商家1",
        ).one()
        legacy_product = Product(
            name="迁移前商家 L40S",
            gpu_model="L40S",
            memory="48GB",
            price=Decimal("1.35"),
            cycle=[30],
            stock=2,
            status="on",
            market_source=None,
            source_price=None,
            supplier_id=supplier.id,
            stock_semantics="supplier_reported_inventory",
        )
        self.db.add(legacy_product)
        self.db.commit()

        data = list_products(
            keyword=None,
            memory=None,
            region=None,
            category=None,
            sort="default",
            min_price=None,
            max_price=None,
            market_source="wod",
            representative=True,
            page=1,
            page_size=100,
            db=self.db,
        )["data"]

        item = next(
            row for row in data["items"] if row["id"] == legacy_product.id
        )
        self.assertEqual(item["market_source"], "wod")
        self.assertEqual(item["seller_type"], "merchant")
        self.assertTrue(item["purchasable"])

    def test_pending_merchant_listing_is_hidden_while_approved_listings_remain_visible(self):
        pending_user = User(
            username="待审核目录商家",
            phone="13900003009",
            password="!",
            supplier_status="pending",
        )
        self.db.add(pending_user)
        self.db.flush()
        pending_supplier = Supplier(
            user_id=pending_user.id,
            company_name="待审核目录商家",
            contact="联系人",
            phone=pending_user.phone,
            status="pending",
        )
        self.db.add(pending_supplier)
        self.db.flush()
        pending_product = Product(
            name="待审核商家 A40",
            gpu_model="A40",
            memory="48GB",
            price=Decimal("0.90"),
            cycle=[],
            stock=10,
            status="on",
            market_source="wod",
            supplier_id=pending_supplier.id,
        )
        self.db.add(pending_product)
        self.db.commit()

        data = list_products(
            keyword=None,
            memory=None,
            region=None,
            category=None,
            sort="default",
            min_price=None,
            max_price=None,
            market_source="wod",
            representative=False,
            page=1,
            page_size=100,
            db=self.db,
        )["data"]
        names = {item["name"] for item in data["items"]}
        self.assertNotIn("待审核商家 A40", names)
        self.assertIn("商家 A40 甲", names)
        self.assertIn("商家 A40 乙", names)
        with self.assertRaises(BizError) as ctx:
            get_product(pending_product.id, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_kai_catalog_fails_closed_without_a_valid_platform_fulfiller(self):
        original = settings.PLATFORM_FULFILLMENT_USER_IDS
        try:
            for configured in ("", "999999999"):
                settings.PLATFORM_FULFILLMENT_USER_IDS = configured
                data = self._list()
                self.assertTrue(data["items"])
                for item in data["items"]:
                    self.assertFalse(item["purchasable"])
                    self.assertEqual(
                        item["purchase_unavailable_reason"],
                        "平台履约暂未配置，当前不可下单",
                    )

            valid_user_id = self.db.query(User.id).first()[0]
            settings.PLATFORM_FULFILLMENT_USER_IDS = str(valid_user_id)
            self.assertTrue(all(item["purchasable"] for item in self._list()["items"]))
        finally:
            settings.PLATFORM_FULFILLMENT_USER_IDS = original


if __name__ == "__main__":
    unittest.main()
