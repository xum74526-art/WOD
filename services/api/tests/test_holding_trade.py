import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (
    Asset,
    HoldingAssetSale,
    Ledger,
    MarketSourceStatus,
    Order,
    OrderFundingAllocation,
    Product,
    User,
    Wallet,
)
from app.routers.asset import asset_detail, my_assets, sell_asset
from app.routers.order import create_order
from app.schemas.asset import AssetSellIn
from app.schemas.order import OrderCreateIn
from app.services.market_sync import utcnow
from app.utils.response import BizError


class HoldingTradeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(phone="13900000111", username="持有测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.user.id,
            balance=Decimal("100"),
            frozen=Decimal("0"),
            promotional_balance=Decimal("1"),
            promotional_frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
            withdraw_frozen=Decimal("0"),
        )
        self.db.add(self.wallet)
        now = utcnow()
        self.source = MarketSourceStatus(
            source="kai",
            enabled=True,
            status="ok",
            refresh_seconds=300,
            sample_count=1,
            last_attempt_at=now,
            last_success_at=now,
        )
        self.product = Product(
            name="KAI RTX 4090",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.1002"),
            source_price=Decimal("0.1002"),
            source_currency="CNY",
            price_updated_at=now,
            cycle=[],
            stock=5,
            status="on",
            market_source="kai",
            external_product_id="holding-kai-4090",
            source_max_configurable_quantity=5,
            platform_stock_cap=5,
        )
        self.db.add_all([self.source, self.product])
        self.db.commit()
        self.original_direct = settings.DIRECT_TRADE_ENABLED
        self.original_holding = settings.HOLDING_TRADE_ENABLED
        self.original_rate = settings.CARD_HOUR_RMB_RATE
        settings.DIRECT_TRADE_ENABLED = True
        settings.HOLDING_TRADE_ENABLED = True
        settings.CARD_HOUR_RMB_RATE = 1.002

    def tearDown(self):
        settings.DIRECT_TRADE_ENABLED = self.original_direct
        settings.HOLDING_TRADE_ENABLED = self.original_holding
        settings.CARD_HOUR_RMB_RATE = self.original_rate
        self.db.close()

    def _buy(self):
        response = create_order(OrderCreateIn(
            product_id=self.product.id,
            quantity=2,
            hours=10,
            purchase_type="holding",
            expected_unit_price_card_hours=Decimal("0.1002"),
            client_request_id="holding-buy-request-0001",
        ), self.user, self.db)
        return response["data"], self.db.query(Asset).filter(Asset.order_id == response["data"]["id"]).one()

    def test_holding_buy_creates_captured_asset_without_delivery(self):
        order_out, asset = self._buy()
        self.db.refresh(self.wallet)
        self.db.refresh(self.product)
        order = self.db.query(Order).filter(Order.id == order_out["id"]).one()
        allocation = self.db.query(OrderFundingAllocation).filter(
            OrderFundingAllocation.order_id == order.id,
        ).one()

        self.assertEqual(order.status, "completed")
        self.assertEqual(order.lifecycle_policy_version, "holding-buyback-v1")
        self.assertIsNone(order.delivery_due_at)
        self.assertEqual(asset.purchase_type, "holding")
        self.assertIsNone(asset.end_at)
        self.assertEqual(allocation.status, "captured")
        self.assertEqual(Decimal(str(self.wallet.balance)), Decimal("97.996000"))
        self.assertEqual(Decimal(str(self.wallet.frozen)), Decimal("0.000000"))
        self.assertEqual(Decimal(str(self.wallet.promotional_balance)), Decimal("0.000000"))
        self.assertEqual(self.product.stock, 3)

    def test_holding_sale_uses_fresh_quote_and_is_idempotent(self):
        _, asset = self._buy()
        self.product.price = Decimal("0.2004")
        self.product.price_updated_at = utcnow()
        self.source.last_success_at = utcnow()
        self.db.commit()

        quote = asset_detail(asset.id, self.user, self.db)["data"]
        self.assertTrue(quote["can_sell"])
        self.assertEqual(quote["current_unit_price"], 0.2004)
        self.assertEqual(quote["current_price"], 4.008)
        self.assertEqual(quote["pnl"], 2.004)
        self.assertEqual(my_assets(None, self.user, self.db)["data"]["total_value"], 4.008)

        request = AssetSellIn(
            client_request_id="holding-sell-request-0001",
            expected_unit_price_card_hours=Decimal("0.2004"),
        )
        first = sell_asset(asset.id, request, self.user, self.db)["data"]
        second = sell_asset(asset.id, request, self.user, self.db)["data"]
        self.db.refresh(self.wallet)
        self.db.refresh(self.product)
        self.db.refresh(asset)

        self.assertEqual(first["sell_price"], 4.008)
        self.assertEqual(second["sell_price"], 4.008)
        self.assertEqual(asset.status, "sold")
        self.assertEqual(Decimal(str(self.wallet.balance)), Decimal("102.004000"))
        self.assertEqual(Decimal(str(self.wallet.promotional_balance)), Decimal("2.000000"))
        self.assertEqual(Decimal(str(self.wallet.withdrawable_balance)), Decimal("0.000000"))
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.db.query(HoldingAssetSale).count(), 1)
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "asset_sale").count(), 1)

    def test_price_change_requires_new_confirmation(self):
        _, asset = self._buy()
        self.product.price = Decimal("0.2004")
        self.product.price_updated_at = utcnow()
        self.source.last_success_at = utcnow()
        self.db.commit()
        with self.assertRaisesRegex(BizError, "价格已更新"):
            sell_asset(asset.id, AssetSellIn(
                client_request_id="holding-sell-request-0002",
                expected_unit_price_card_hours=Decimal("0.1"),
            ), self.user, self.db)
        self.db.refresh(asset)
        self.db.refresh(self.wallet)
        self.assertEqual(asset.status, "active")
        self.assertEqual(Decimal(str(self.wallet.balance)), Decimal("97.996000"))

    def test_stale_quote_blocks_sale(self):
        _, asset = self._buy()
        stale = utcnow() - timedelta(hours=1)
        self.product.price_updated_at = stale
        self.source.last_success_at = stale
        self.db.commit()
        detail = asset_detail(asset.id, self.user, self.db)["data"]
        self.assertFalse(detail["can_sell"])
        with self.assertRaises(BizError):
            sell_asset(asset.id, AssetSellIn(
                client_request_id="holding-sell-request-0003",
                expected_unit_price_card_hours=Decimal("0.1002"),
            ), self.user, self.db)

    def test_feature_switch_blocks_new_holding_without_mutation(self):
        settings.HOLDING_TRADE_ENABLED = False
        with self.assertRaises(BizError):
            self._buy()
        self.db.refresh(self.wallet)
        self.db.refresh(self.product)
        self.assertEqual(Decimal(str(self.wallet.balance)), Decimal("100.000000"))
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(self.db.query(Order).count(), 0)


if __name__ == "__main__":
    unittest.main()
