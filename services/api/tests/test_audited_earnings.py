import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import *  # noqa: F401,F403 - register complete test metadata
from app.models.asset import Asset
from app.models.holding_asset_sale import HoldingAssetSale
from app.models.market_price import MarketSourceStatus
from app.models.order import Order
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.reward_accrual import RewardAccrual
from app.models.user import User
from app.models.wallet import Wallet
from app.routers.asset import my_assets
from app.routers.wallet import wallet_info
from app.services.audited_earnings import (
    audited_earnings_chart,
    audited_earnings_records,
    audited_earnings_summary,
)
from app.services.reward_program import PROGRAM_CONSUMER


class AuditedEarningsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.original_direct = settings.DIRECT_TRADE_ENABLED
        self.original_holding = settings.HOLDING_TRADE_ENABLED
        self.original_rate = settings.CARD_HOUR_RMB_RATE
        self.original_timezone = settings.REWARD_TIMEZONE
        settings.DIRECT_TRADE_ENABLED = True
        settings.HOLDING_TRADE_ENABLED = True
        settings.CARD_HOUR_RMB_RATE = 1.002
        settings.REWARD_TIMEZONE = "Asia/Shanghai"

        # Production DateTime columns store naive UTC values.
        self.now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        self.user = User(username="earnings-user", phone="13900009001", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id, balance=Decimal("0"), frozen=Decimal("0"))
        self.product = Product(
            name="KAI RTX 4090",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.2004"),
            source_price=Decimal("0.2004"),
            source_currency="CNY",
            price_updated_at=self.now,
            cycle=[],
            stock=10,
            status="on",
            market_source="kai",
            external_product_id="earnings-kai-4090",
        )
        self.source = MarketSourceStatus(
            source="kai",
            enabled=True,
            status="ok",
            refresh_seconds=300,
            sample_count=1,
            last_attempt_at=self.now,
            last_success_at=self.now,
        )
        self.db.add_all([self.wallet, self.product, self.source])
        self.db.flush()

        usage_order = self._order("USAGE1", Decimal("100"), "usage")
        usage_asset = Asset(
            user_id=self.user.id,
            product_id=self.product.id,
            order_id=usage_order.id,
            quantity=1,
            value=Decimal("100"),
            daily_rate=Decimal("0"),
            status="active",
            purchase_type="usage",
            start_at=self.now - timedelta(days=3),
            end_at=self.now + timedelta(days=2),
        )
        self.db.add(usage_asset)
        self.db.flush()
        settled_at = self.now - timedelta(days=1)
        self.db.add_all([
            RewardAccrual(
                program_code=PROGRAM_CONSUMER,
                policy_version="consumer-monthly-tier-v1",
                beneficiary_user_id=self.user.id,
                source_type="order",
                source_id=usage_order.id,
                order_id=usage_order.id,
                asset_id=usage_asset.id,
                period_key=settled_at.strftime("%Y-%m"),
                base_amount=Decimal("100"),
                rate_bps=300,
                reward_amount=Decimal("3"),
                policy_snapshot={},
                due_at=settled_at,
                status="settled",
                settled_at=settled_at,
                idempotency_key="earnings-settled-rebate",
            ),
            RewardAccrual(
                program_code=PROGRAM_CONSUMER,
                policy_version="consumer-monthly-tier-v1",
                beneficiary_user_id=self.user.id,
                source_type="renewal",
                source_id=9002,
                order_id=usage_order.id,
                asset_id=usage_asset.id,
                period_key=self.now.strftime("%Y-%m"),
                base_amount=Decimal("100"),
                rate_bps=400,
                reward_amount=Decimal("4"),
                policy_snapshot={},
                due_at=self.now + timedelta(days=2),
                status="pending",
                idempotency_key="earnings-pending-rebate",
            ),
            # A legacy simulator row must remain audit-only and never enter
            # current earnings totals, chart or records.
            Revenue(
                asset_id=usage_asset.id,
                user_id=self.user.id,
                amount=Decimal("99"),
                date=self.now.date(),
            ),
        ])

        active_order = self._order("HOLDING1", Decimal("2"), "holding")
        active_order.lifecycle_policy_version = "holding-buyback-v1"
        self.active_holding = Asset(
            user_id=self.user.id,
            product_id=self.product.id,
            order_id=active_order.id,
            quantity=2,
            value=Decimal("1"),
            daily_rate=Decimal("0"),
            status="active",
            purchase_type="holding",
            start_at=self.now,
        )
        sold_order = self._order("HOLDING2", Decimal("3"), "holding")
        sold_order.lifecycle_policy_version = "holding-buyback-v1"
        sold_asset = Asset(
            user_id=self.user.id,
            product_id=self.product.id,
            order_id=sold_order.id,
            quantity=1,
            value=Decimal("3"),
            daily_rate=Decimal("0"),
            status="sold",
            purchase_type="holding",
            start_at=self.now - timedelta(days=2),
        )
        self.db.add_all([self.active_holding, sold_asset])
        self.db.flush()
        self.db.add(HoldingAssetSale(
            event_key="holding_asset_sale:test-earnings",
            client_request_id="earnings-sale-request-0001",
            asset_id=sold_asset.id,
            order_id=sold_order.id,
            user_id=self.user.id,
            wallet_id=self.wallet.id,
            product_id=self.product.id,
            quantity=1,
            purchase_hours=10,
            market_source="kai",
            unit_price_cny_per_gpu_hour=Decimal("0.4509"),
            unit_price_card_hours_per_gpu_hour=Decimal("0.45"),
            buy_value_card_hours=Decimal("3"),
            sell_value_card_hours=Decimal("4.5"),
            pnl_card_hours=Decimal("1.5"),
            cash_value_card_hours=Decimal("4.5"),
            promotional_value_card_hours=Decimal("0"),
            price_observed_at=self.now,
            policy_version="holding-buyback-settlement-v1",
            policy_snapshot={},
            settled_at=self.now,
        ))
        self.db.commit()

    def tearDown(self):
        settings.DIRECT_TRADE_ENABLED = self.original_direct
        settings.HOLDING_TRADE_ENABLED = self.original_holding
        settings.CARD_HOUR_RMB_RATE = self.original_rate
        settings.REWARD_TIMEZONE = self.original_timezone
        self.db.close()
        self.engine.dispose()

    def _order(self, number: str, amount: Decimal, purchase_type: str) -> Order:
        order = Order(
            order_no=number,
            client_request_id=f"request-{number.lower()}-0001",
            user_id=self.user.id,
            product_id=self.product.id,
            quantity=2 if purchase_type == "holding" and number == "HOLDING1" else 1,
            purchase_hours=10,
            cycle_days=0,
            amount=amount,
            status="completed",
            purchase_type=purchase_type,
            start_at=self.now,
        )
        self.db.add(order)
        self.db.flush()
        return order

    def test_summary_uses_real_rebate_and_holding_facts_only(self):
        summary = audited_earnings_summary(self.user.id, self.db)

        self.assertEqual(summary["settled_rebate_total"], 3.0)
        self.assertEqual(summary["pending_rebate"], 4.0)
        self.assertEqual(summary["holding_realized_pnl"], 1.5)
        self.assertEqual(summary["holding_unrealized_pnl"], 2.0)
        self.assertEqual(summary["holding_unrealized_pnl_rate"], 100.0)
        self.assertEqual(summary["today"], 1.5)
        self.assertEqual(summary["total"], 4.5)
        self.assertEqual(summary["historical_test_total"], 99.0)
        self.assertEqual(summary["holding_priced_assets"], 1)
        self.assertEqual(wallet_info(self.user, self.db)["data"]["total_income"], 4.5)
        asset_summary = my_assets(None, self.user, self.db)["data"]
        self.assertEqual(asset_summary["pending_revenue"], 4.0)
        self.assertTrue(asset_summary["audited_earnings_enabled"])
        usage_asset = next(item for item in asset_summary["items"] if item["purchase_type"] == "usage")
        self.assertEqual(usage_asset["rebate_status"], "pending")
        self.assertEqual(usage_asset["rebate_amount"], 7.0)
        self.assertEqual(usage_asset["pending_rebate"], 4.0)
        self.assertEqual(usage_asset["settled_rebate"], 3.0)

    def test_chart_and_records_exclude_legacy_simulator_rows(self):
        chart = audited_earnings_chart(self.user.id, 3, self.db)
        self.assertEqual(len(chart), 3)
        self.assertEqual(chart[-1]["amount"], 4.5)
        records = audited_earnings_records(self.user.id, self.db)
        self.assertEqual({row["source_type"] for row in records}, {"consumer_rebate", "holding_sale"})
        self.assertEqual(sum(Decimal(str(row["amount"])) for row in records), Decimal("4.5"))
        self.assertTrue(all(row["record_key"] for row in records))


if __name__ == "__main__":
    unittest.main()
