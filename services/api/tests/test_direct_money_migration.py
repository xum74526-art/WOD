import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.holding_asset_sale import HoldingAssetSale
from app.models.merchant_settlement import MerchantSettlement
from app.models.order import Order
from app.models.order_funding import OrderFundingAllocation
from app.models.order_renewal import OrderRenewal
from app.models.payment import PaymentOrder
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.wallet import Wallet
from init_db import _migrate_legacy_card_hours_to_cny


class DirectMoneyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

        user = User(phone="13900000088", username="money-migration", password="!")
        self.db.add(user)
        self.db.flush()
        wallet = Wallet(
            user_id=user.id,
            balance=Decimal("99.800400"),
            frozen=Decimal("1.000000"),
            withdrawable_balance=Decimal("2.000000"),
            withdraw_frozen=Decimal("0.500000"),
            promotional_balance=Decimal("3.000000"),
            promotional_frozen=Decimal("0.250000"),
        )
        self.db.add(wallet)
        self.db.flush()
        kai = Product(
            name="KAI H100",
            gpu_model="H100",
            memory="80GB",
            price=Decimal("10.0000"),
            market_source="kai",
            stock=1,
            status="on",
        )
        merchant = Product(
            name="Supplier A100",
            gpu_model="A100",
            memory="40GB",
            price=Decimal("10.0000"),
            market_source="wod",
            stock=1,
            status="on",
        )
        self.db.add_all([kai, merchant])
        self.db.flush()
        self.db.add_all([
            PriceHistory(product_id=kai.id, gpu_model="H100", price=Decimal("10.0000")),
            PriceHistory(product_id=merchant.id, gpu_model="A100", price=Decimal("10.0000")),
        ])
        order = Order(
            order_no="WOD-MONEY-MIGRATION-1",
            user_id=user.id,
            product_id=merchant.id,
            amount=Decimal("5.0000"),
            coupon_discount=Decimal("1.000000"),
            quantity=1,
            purchase_hours=5,
            product_snapshot={"confirmed_unit_price_card_hours": "1.000000"},
        )
        self.db.add(order)
        self.db.flush()
        self.db.add(Asset(
            user_id=user.id,
            product_id=merchant.id,
            order_id=order.id,
            value=Decimal("5.0000"),
            daily_rate=Decimal("0.030000"),
            sell_price=4.0,
            rebate_amount=0.5,
        ))
        self.db.add(Ledger(
            user_id=user.id,
            wallet_id=wallet.id,
            type="pay",
            direction="out",
            amount=Decimal("5.000000"),
            balance_after=Decimal("99.800400"),
        ))
        self.db.add(OrderFundingAllocation(
            source_type="order",
            source_id=order.id,
            order_id=order.id,
            user_id=user.id,
            wallet_id=wallet.id,
            gross_amount=Decimal("5.000000"),
            cash_amount=Decimal("3.000000"),
            promotional_amount=Decimal("2.000000"),
            policy_version="legacy-test",
            status="captured",
            policy_snapshot={},
        ))
        self.db.add(HoldingAssetSale(
            event_key="holding-money-migration",
            client_request_id="holding-money-migration",
            asset_id=1,
            order_id=order.id,
            user_id=user.id,
            wallet_id=wallet.id,
            product_id=merchant.id,
            quantity=1,
            purchase_hours=5,
            market_source="kai",
            unit_price_cny_per_gpu_hour=Decimal("2.000000"),
            unit_price_card_hours_per_gpu_hour=Decimal("1.996008"),
            buy_value_card_hours=Decimal("5.000000"),
            sell_value_card_hours=Decimal("4.000000"),
            pnl_card_hours=Decimal("-1.000000"),
            cash_value_card_hours=Decimal("3.000000"),
            promotional_value_card_hours=Decimal("1.000000"),
            price_observed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            policy_version="legacy-test",
            policy_snapshot={},
            settled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        self.db.add(MerchantSettlement(
            event_key="merchant-money-migration",
            policy_version="legacy-test",
            source_type="order",
            source_id=order.id,
            order_id=order.id,
            buyer_user_id=user.id,
            supplier_id=1,
            supplier_user_id=user.id,
            wallet_id=wallet.id,
            gross_amount=Decimal("5.000000"),
            service_fee_bps=1000,
            service_fee_amount=Decimal("0.500000"),
            net_amount=Decimal("4.500000"),
            policy_snapshot={},
            status="settled",
            settled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        renewal = OrderRenewal(
            order_id=order.id,
            user_id=user.id,
            client_request_id="renew-money-migration",
            purchase_hours=1,
            quantity=1,
            amount=Decimal("1.0000"),
            new_end_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
            total_amount_after=Decimal("6.0000"),
            response_payload={
                "amount": 6,
                "amount_card_hours": 6,
                "price_cny_per_gpu_hour": 1.002,
                "nested": {"renewal_amount_card_hours": 1},
            },
        )
        self.db.add(renewal)
        self.db.add(PaymentOrder(
            order_no="PAY-MONEY-MIGRATION-1",
            user_id=user.id,
            provider="mapay",
            status="paid",
            amount_cny=Decimal("0.01"),
            card_hours=Decimal("0.009980"),
            card_hour_rate=Decimal("1.002000"),
            checkout_token_hash="money-migration-token",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_complete_conversion_is_audited_and_idempotent(self):
        first = _migrate_legacy_card_hours_to_cny(self.engine, self.db)
        self.assertTrue(first["applied"])
        self.assertEqual(first["factor"], "1.002")

        self.db.expire_all()
        wallet = self.db.query(Wallet).one()
        self.assertEqual(wallet.balance, Decimal("100.000001"))
        self.assertEqual(wallet.frozen, Decimal("1.002000"))
        self.assertEqual(wallet.withdrawable_balance, Decimal("2.004000"))
        self.assertEqual(wallet.promotional_balance, Decimal("3.006000"))
        ledger = self.db.query(Ledger).one()
        self.assertEqual(ledger.amount, Decimal("5.010000"))
        self.assertEqual(ledger.balance_after, Decimal("100.000001"))

        kai, merchant = self.db.query(Product).order_by(Product.id.asc()).all()
        self.assertEqual(kai.price, Decimal("10.0000"))
        self.assertEqual(merchant.price, Decimal("10.0200"))
        kai_history, merchant_history = self.db.query(PriceHistory).order_by(
            PriceHistory.id.asc()
        ).all()
        self.assertEqual(kai_history.price, Decimal("10.0000"))
        self.assertEqual(merchant_history.price, Decimal("10.0200"))

        order = self.db.query(Order).one()
        self.assertEqual(order.amount, Decimal("5.0100"))
        self.assertEqual(order.coupon_discount, Decimal("1.002000"))
        self.assertEqual(
            order.product_snapshot["confirmed_unit_price_card_hours"],
            "1.002000",
        )
        self.assertEqual(order.product_snapshot["settlement_currency"], "CNY")
        asset = self.db.query(Asset).one()
        self.assertEqual(asset.value, Decimal("5.0100"))
        self.assertEqual(asset.daily_rate, Decimal("0.030000"))
        self.assertAlmostEqual(asset.sell_price, 4.008)
        self.assertAlmostEqual(asset.rebate_amount, 0.501)

        renewal = self.db.query(OrderRenewal).one()
        self.assertEqual(renewal.amount, Decimal("1.0020"))
        self.assertEqual(renewal.total_amount_after, Decimal("6.0120"))
        self.assertEqual(renewal.response_payload["amount"], 6.012)
        self.assertEqual(renewal.response_payload["amount_card_hours"], 6.012)
        self.assertEqual(renewal.response_payload["price_cny_per_gpu_hour"], 1.002)
        self.assertEqual(
            renewal.response_payload["nested"]["renewal_amount_card_hours"],
            1.002,
        )

        payment = self.db.query(PaymentOrder).one()
        self.assertEqual(payment.amount_cny, Decimal("0.01"))
        self.assertEqual(payment.card_hours, Decimal("0.010000"))
        self.assertEqual(payment.card_hour_rate, Decimal("1.000000"))

        allocation = self.db.query(OrderFundingAllocation).one()
        self.assertEqual(allocation.cash_amount, Decimal("3.006000"))
        self.assertEqual(allocation.promotional_amount, Decimal("2.004000"))
        self.assertEqual(
            allocation.gross_amount,
            allocation.cash_amount + allocation.promotional_amount,
        )
        sale = self.db.query(HoldingAssetSale).one()
        self.assertEqual(sale.unit_price_card_hours_per_gpu_hour, Decimal("2.000000"))
        self.assertEqual(
            sale.sell_value_card_hours,
            sale.cash_value_card_hours + sale.promotional_value_card_hours,
        )
        self.assertEqual(
            sale.pnl_card_hours,
            sale.sell_value_card_hours - sale.buy_value_card_hours,
        )
        settlement = self.db.query(MerchantSettlement).one()
        self.assertEqual(
            settlement.gross_amount,
            settlement.service_fee_amount + settlement.net_amount,
        )

        audit = self.db.execute(text(
            "SELECT from_unit, to_unit, conversion_factor, details "
            "FROM app_migration_audits WHERE name = "
            "'20260929_legacy_card_hours_to_direct_cny_v1'"
        )).one()
        self.assertEqual(tuple(audit[:3]), ("CARD_HOUR", "CNY", "1.002"))
        self.assertIn("wallets", json.loads(audit.details))

        second = _migrate_legacy_card_hours_to_cny(self.engine, self.db)
        self.assertFalse(second["applied"])
        self.db.expire_all()
        self.assertEqual(self.db.query(Wallet).one().balance, Decimal("100.000001"))
        marker_count = self.db.execute(text(
            "SELECT COUNT(*) FROM app_migrations WHERE name = "
            "'20260929_legacy_card_hours_to_direct_cny_v1'"
        )).scalar_one()
        self.assertEqual(marker_count, 1)


if __name__ == "__main__":
    unittest.main()
