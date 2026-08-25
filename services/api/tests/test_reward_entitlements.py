import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import *  # noqa: F401,F403 - register complete test metadata
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.order import Order
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.reward_accrual import RewardAccrual
from app.models.supplier import Supplier
from app.models.user import User
from app.models.wallet import Wallet
from app.services.reward_entitlements import (
    CONSUMER_POLICY_VERSION,
    PROGRAM_CONSUMER,
    PROGRAM_INVITE,
    PROGRAM_SUPPLIER,
    SUPPLIER_POLICY_VERSION,
    create_consumer_order_accrual,
    create_consumer_renewal_accrual,
    create_invite_accrual,
    create_supplier_order_accrual,
    get_consumer_summary,
    get_supplier_summary,
    settle_reward_entitlements,
)
from app.services.reward_program import assert_reward_configuration_safe
from app.services.wallet_balance import spendable_wallet_balance


class RewardEntitlementTests(unittest.TestCase):
    SWITCHES = (
        "REWARD_SERVICE_ENABLED",
        "CLOSED_TEST_REWARD_ENABLED",
        "CONSUMER_REWARD_ENABLED",
        "SUPPLIER_REWARD_ENABLED",
        "INVITE_REWARD_ENABLED",
        "REWARD_SETTLEMENT_ENABLED",
    )

    def setUp(self):
        self.original_switches = {name: getattr(settings, name) for name in self.SWITCHES}
        self.original_reward_timezone = settings.REWARD_TIMEZONE
        for name in self.SWITCHES:
            setattr(settings, name, False)
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

        self.buyer = User(username="reward-buyer", phone="13900003001", password="!")
        self.seller = User(
            username="reward-seller", phone="13900003002", password="!",
            role="supplier", supplier_status="approved",
        )
        self.inviter = User(username="reward-inviter", phone="13900003003", password="!")
        self.db.add_all([self.buyer, self.seller, self.inviter])
        self.db.flush()
        self.db.add_all([
            Wallet(user_id=self.buyer.id, balance=Decimal("0"), frozen=Decimal("0")),
            Wallet(user_id=self.seller.id, balance=Decimal("0"), frozen=Decimal("0")),
            Wallet(user_id=self.inviter.id, balance=Decimal("0"), frozen=Decimal("0")),
        ])
        self.supplier = Supplier(
            user_id=self.seller.id, company_name="Reward Supplier", contact="Seller",
            phone=self.seller.phone, status="approved",
        )
        self.db.add(self.supplier)
        self.db.flush()
        self.product = Product(
            name="Reward GPU", gpu_model="H100", memory="80GB",
            price=Decimal("1"), cycle=[], stock=100, status="on",
            supplier_id=self.supplier.id,
        )
        self.db.add(self.product)
        self.db.commit()
        self.sequence = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        for name, value in self.original_switches.items():
            setattr(settings, name, value)
        settings.REWARD_TIMEZONE = self.original_reward_timezone

    def _order(self, amount: Decimal | str, *, user_id: int | None = None) -> Order:
        self.sequence += 1
        order = Order(
            order_no=f"REWARD{self.sequence:08d}",
            user_id=user_id or self.buyer.id,
            product_id=self.product.id,
            quantity=1,
            purchase_hours=24,
            cycle_days=0,
            amount=Decimal(str(amount)),
            status="completed",
            purchase_type="usage",
            start_at=self.now,
            end_at=self.now + timedelta(hours=24),
        )
        self.db.add(order)
        self.db.flush()
        return order

    def _asset(self, order: Order, *, end_at=None) -> Asset:
        asset = Asset(
            user_id=order.user_id,
            product_id=order.product_id,
            order_id=order.id,
            quantity=order.quantity,
            value=order.amount,
            daily_rate=Decimal("0"),
            status="active",
            purchase_type="usage",
            start_at=self.now,
            end_at=end_at or order.end_at,
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def test_startup_rejects_retired_legacy_writers(self):
        settings.REWARD_SERVICE_ENABLED = True
        with self.assertRaisesRegex(RuntimeError, "legacy reward writers are retired"):
            assert_reward_configuration_safe()

        settings.REWARD_SERVICE_ENABLED = False
        settings.CLOSED_TEST_REWARD_ENABLED = True
        with self.assertRaisesRegex(RuntimeError, "legacy reward writers are retired"):
            assert_reward_configuration_safe()

        settings.CLOSED_TEST_REWARD_ENABLED = False
        settings.CONSUMER_REWARD_ENABLED = True
        settings.SUPPLIER_REWARD_ENABLED = True
        assert_reward_configuration_safe()

        settings.REWARD_TIMEZONE = "Mars/Olympus_Mons"
        with self.assertRaisesRegex(RuntimeError, "invalid REWARD_TIMEZONE"):
            assert_reward_configuration_safe()

    def test_consumer_snapshot_idempotency_and_settlement_survive_writer_disable(self):
        settings.CONSUMER_REWARD_ENABLED = True
        order = self._order("100")
        asset = self._asset(order)

        first = create_consumer_order_accrual(order, asset, self.now, self.db)
        duplicate = create_consumer_order_accrual(order, asset, self.now, self.db)
        with patch(
            "app.services.reward_entitlements.CONSUMER_POLICY_VERSION",
            "consumer-monthly-tier-v2",
        ):
            replay_after_policy_upgrade = create_consumer_order_accrual(
                order, asset, self.now, self.db,
            )
        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(first.id, replay_after_policy_upgrade.id)
        self.assertEqual(self.db.query(RewardAccrual).count(), 1)
        self.assertEqual(first.policy_version, CONSUMER_POLICY_VERSION)
        self.assertEqual(first.rate_bps, 300)
        self.assertEqual(first.reward_amount, Decimal("3.000000"))
        self.assertEqual(first.policy_snapshot["projected_month_spent"], 100.0)
        self.assertIsNone(create_supplier_order_accrual(order, self.now, self.db))

        # Turning the writer off must not erase or strand an existing promise.
        settings.CONSUMER_REWARD_ENABLED = False
        settings.REWARD_SETTLEMENT_ENABLED = True
        expired = self.now - timedelta(minutes=1)
        asset.end_at = expired
        first.due_at = expired
        self.assertEqual(settle_reward_entitlements(self.db, self.now), 1)
        self.assertEqual(settle_reward_entitlements(self.db, self.now), 0)

        wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.assertEqual(wallet.balance, Decimal("3.000000"))
        ledger = self.db.query(Ledger).filter(
            Ledger.ref_reward_accrual_id == first.id,
        ).one()
        self.assertEqual(ledger.type, "consumer_purchase_rebate")
        self.assertEqual(ledger.ref_order_id, order.id)
        summary = get_consumer_summary(self.buyer.id, self.db)
        self.assertFalse(summary["rewards_enabled"])
        self.assertEqual(summary["month_entitled"], 3.0)
        self.assertEqual(summary["month_rebated"], 3.0)
        self.assertEqual(summary["cap_used"], 3.0)
        self.assertEqual(summary["cap_remaining"], 19997.0)

    def test_renewal_extends_all_due_dates_and_uses_independent_ledger_reference(self):
        settings.CONSUMER_REWARD_ENABLED = True
        order = self._order("100")
        asset = self._asset(order)
        original = create_consumer_order_accrual(order, asset, self.now, self.db)

        new_end = self.now + timedelta(hours=48)
        renewal = OrderRenewal(
            order_id=order.id,
            user_id=self.buyer.id,
            client_request_id="reward-renewal-0001",
            purchase_hours=24,
            cycle_days=None,
            quantity=1,
            amount=Decimal("50"),
            previous_end_at=asset.end_at,
            new_end_at=new_end,
            total_amount_after=Decimal("150"),
            total_purchase_hours_after=48,
            total_cycle_days_after=None,
            response_payload={},
        )
        self.db.add(renewal)
        self.db.flush()
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.db.add(Ledger(
            user_id=self.buyer.id,
            wallet_id=buyer_wallet.id,
            type="pay",
            direction="out",
            amount=renewal.amount,
            balance_after=buyer_wallet.balance,
            ref_order_renewal_id=renewal.id,
            event_key=f"order_renewal:{renewal.id}",
            remark="renewal debit",
        ))
        asset.end_at = new_end
        order.end_at = new_end
        order.status = "running"
        renewed = create_consumer_renewal_accrual(order, renewal, asset, self.now, self.db)
        self.db.refresh(original)
        original_due = original.due_at.replace(tzinfo=timezone.utc) if original.due_at.tzinfo is None else original.due_at
        renewed_due = renewed.due_at.replace(tzinfo=timezone.utc) if renewed.due_at.tzinfo is None else renewed.due_at
        self.assertEqual(original_due, new_end)
        self.assertEqual(renewed_due, new_end)
        self.assertEqual(renewed.reward_amount, Decimal("1.500000"))

        expired = self.now - timedelta(minutes=1)
        asset.end_at = expired
        original.due_at = expired
        renewed.due_at = expired
        settings.REWARD_SETTLEMENT_ENABLED = True
        self.assertEqual(settle_reward_entitlements(self.db, self.now), 2)
        rewards = self.db.query(Ledger).filter(
            Ledger.ref_reward_accrual_id.isnot(None),
        ).order_by(Ledger.id).all()
        self.assertEqual(len(rewards), 2)
        self.assertTrue(all(item.ref_order_renewal_id is None for item in rewards))
        self.assertEqual(
            self.db.query(Ledger).filter(Ledger.ref_order_renewal_id == renewal.id).count(),
            1,
        )
        self.assertEqual({item.ref_reward_accrual_id for item in rewards}, {original.id, renewed.id})

    def test_supplier_uses_full_monthly_sales_increment_and_cap(self):
        settings.SUPPLIER_REWARD_ENABLED = True
        settings.REWARD_SETTLEMENT_ENABLED = True

        first = create_supplier_order_accrual(self._order("100"), self.now, self.db)
        second = create_supplier_order_accrual(self._order("10000"), self.now, self.db)
        capped = create_supplier_order_accrual(self._order("400000"), self.now, self.db)
        self.assertEqual(first.policy_version, SUPPLIER_POLICY_VERSION)
        self.assertEqual(first.reward_amount, Decimal("5.000000"))
        self.assertEqual(second.rate_bps, 800)
        self.assertEqual(second.policy_snapshot["monthly_target"], 808.0)
        self.assertEqual(second.reward_amount, Decimal("803.000000"))
        self.assertEqual(capped.rate_bps, 1500)
        self.assertEqual(capped.reward_amount, Decimal("49192.000000"))

        summary = get_supplier_summary(self.seller.id, self.db)
        self.assertEqual(summary["month_sales"], 410100.0)
        self.assertEqual(summary["month_entitled"], 50000.0)
        self.assertEqual(summary["month_rebated"], 50000.0)
        self.assertEqual(summary["cap_used"], 50000.0)
        self.assertEqual(summary["cap_remaining"], 0.0)
        self.assertEqual(summary["service_fee_rate"], 100)

        self_purchase = self._order("100", user_id=self.seller.id)
        self.assertIsNone(create_supplier_order_accrual(self_purchase, self.now, self.db))
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code == PROGRAM_SUPPLIER,
        ).count(), 3)

    def test_consumer_cap_and_legacy_rows_remain_isolated(self):
        legacy_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        legacy_wallet.balance = Decimal("13")
        self.db.add_all([
            Ledger(
                user_id=self.buyer.id,
                wallet_id=legacy_wallet.id,
                type="rebate",
                direction="in",
                amount=Decimal("7"),
                balance_after=legacy_wallet.balance,
                remark="legacy synthetic reward",
            ),
            Ledger(
                user_id=self.buyer.id,
                wallet_id=legacy_wallet.id,
                type="test_rebate",
                direction="in",
                amount=Decimal("6"),
                balance_after=legacy_wallet.balance,
                remark="legacy closed-test reward",
            ),
        ])
        legacy_asset = self._asset(self._order("1"), end_at=self.now - timedelta(days=1))
        legacy_asset.rebate_status = "pending"
        legacy_asset.rebate_amount = 99
        self.db.flush()
        self.assertEqual(spendable_wallet_balance(legacy_wallet, self.db), Decimal("0"))

        settings.CONSUMER_REWARD_ENABLED = True
        order = self._order("300000")
        asset = self._asset(order, end_at=self.now - timedelta(minutes=1))
        accrual = create_consumer_order_accrual(order, asset, self.now, self.db)
        self.assertEqual(accrual.rate_bps, 1000)
        self.assertEqual(accrual.reward_amount, Decimal("20000.000000"))
        summary = get_consumer_summary(self.buyer.id, self.db)
        self.assertEqual(summary["cap_used"], 20000.0)
        self.assertEqual(summary["cap_remaining"], 0.0)

        settings.REWARD_SETTLEMENT_ENABLED = True
        self.assertEqual(settle_reward_entitlements(self.db, self.now), 1)
        self.db.refresh(legacy_asset)
        self.assertEqual(legacy_asset.rebate_status, "pending")
        self.assertEqual(self.db.query(Ledger).filter(
            Ledger.type.in_(("rebate", "test_rebate")),
        ).count(), 2)
        self.assertEqual(spendable_wallet_balance(legacy_wallet, self.db), Decimal("20000.000000"))

    def test_invite_writer_and_settler_are_independent(self):
        settings.INVITE_REWARD_ENABLED = True
        order = self._order("100")
        accrual = create_invite_accrual(
            beneficiary_user_id=self.inviter.id,
            order=order,
            rate_bps=1500,
            event_at=self.now,
            db=self.db,
        )
        self.assertEqual(accrual.program_code, PROGRAM_INVITE)
        self.assertEqual(accrual.status, "pending")
        self.assertIsNone(create_consumer_order_accrual(order, self._asset(order), self.now, self.db))
        self.assertIsNone(create_supplier_order_accrual(order, self.now, self.db))

        settings.INVITE_REWARD_ENABLED = False
        settings.REWARD_SETTLEMENT_ENABLED = True
        self.assertEqual(settle_reward_entitlements(self.db, self.now), 1)
        self.db.refresh(accrual)
        self.assertEqual(accrual.status, "settled")
        ledger = self.db.query(Ledger).filter(
            Ledger.ref_reward_accrual_id == accrual.id,
        ).one()
        self.assertEqual(ledger.type, "invite_first_order_reward")
        self.assertEqual(ledger.amount, Decimal("15.000000"))


if __name__ == "__main__":
    unittest.main()
