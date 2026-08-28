import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import Asset, Ledger, MerchantSettlement, Order, Product, Supplier, User, Wallet  # noqa: F401
from app.routers.order import (
    cancel_order,
    confirm_delivery,
    create_order,
    deliver_ssh,
    dispute_delivery,
    resolve_delivery_dispute,
)
from app.schemas.order import (
    OrderCreateIn,
    OrderDeliverIn,
    OrderDisputeIn,
    OrderDisputeResolveIn,
)
from app.services.lifecycle import _restore_expired_order_stock, process_order_lifecycle
from app.services.merchant_settlement import (
    MerchantSettlementError,
    assert_merchant_settlement_configuration_safe,
)
from app.utils.response import BizError


class OrderFulfillmentLifecycleTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.original = {
            name: getattr(settings, name)
            for name in (
                "CONSUMER_REWARD_ENABLED",
                "SUPPLIER_REWARD_ENABLED",
                "INVITE_REWARD_ENABLED",
                "REWARD_SETTLEMENT_ENABLED",
                "DIRECT_TRADE_ENABLED",
                "ORDER_DELIVERY_TIMEOUT_HOURS",
                "ORDER_CONFIRMATION_TIMEOUT_HOURS",
                "ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS",
                "ORDER_LEGACY_PENDING_MIGRATION_ENABLED",
                "MERCHANT_SERVICE_FEE_BPS",
            )
        }
        settings.CONSUMER_REWARD_ENABLED = False
        settings.SUPPLIER_REWARD_ENABLED = False
        settings.INVITE_REWARD_ENABLED = False
        settings.REWARD_SETTLEMENT_ENABLED = False
        settings.DIRECT_TRADE_ENABLED = True
        settings.ORDER_DELIVERY_TIMEOUT_HOURS = 24
        settings.ORDER_CONFIRMATION_TIMEOUT_HOURS = 24
        settings.ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS = 72
        settings.ORDER_LEGACY_PENDING_MIGRATION_ENABLED = False
        settings.MERCHANT_SERVICE_FEE_BPS = 1000

        self.buyer = User(phone="13900002001", username="买家", password="!")
        self.seller = User(
            phone="13900002002",
            username="商家",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.admin = User(phone="13900002003", username="管理员", password="!", role="admin")
        self.db.add_all([self.buyer, self.seller, self.admin])
        self.db.flush()
        self.buyer_wallet = Wallet(user_id=self.buyer.id, balance=Decimal("100"), frozen=Decimal("0"))
        self.seller_wallet = Wallet(
            user_id=self.seller.id,
            balance=Decimal("0"),
            frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
        )
        self.db.add_all([self.buyer_wallet, self.seller_wallet])
        self.supplier = Supplier(
            user_id=self.seller.id,
            company_name="生命周期商家",
            contact="商家",
            phone="13900002002",
            status="approved",
        )
        self.db.add(self.supplier)
        self.db.flush()
        self.product = Product(
            name="RTX 4090 生命周期测试",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.01"),
            cycle=[30],
            stock=1,
            supplier_id=self.supplier.id,
            market_source="wod",
            status="on",
        )
        self.db.add(self.product)
        self.db.commit()

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()

    def _order(self) -> Order:
        payload = OrderCreateIn(
            product_id=self.product.id,
            quantity=1,
            cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.01"),
            purchase_type="usage",
            client_request_id=f"lifecycle-order-{self.db.query(Order).count() + 1:04d}",
        )
        result = create_order(payload, self.buyer, self.db, "android")
        return self.db.get(Order, result["data"]["id"])

    def _deliver(self, order: Order) -> Order:
        deliver_ssh(
            order.id,
            OrderDeliverIn(ssh_info="ssh ubuntu@192.0.2.80 -p 22"),
            self.seller,
            self.db,
            "android",
        )
        self.db.refresh(order)
        return order

    def test_dispute_refund_preserves_frozen_funds_until_resolution(self):
        order = self._deliver(self._order())
        dispute_delivery(
            order.id,
            OrderDisputeIn(reason="交付的 SSH 无法建立连接"),
            self.buyer,
            self.db,
            "ios",
        )
        self.db.refresh(order)
        self.db.refresh(self.buyer_wallet)
        self.assertEqual(order.status, "disputed")
        self.assertEqual(self.buyer_wallet.frozen, Decimal("7.2000"))
        self.assertEqual(self.db.query(MerchantSettlement).count(), 0)

        payload = OrderDisputeResolveIn(action="refund", note="核验连接失败，支持买家退款")
        resolve_delivery_dispute(order.id, payload, self.admin, self.db, "admin")
        repeat = resolve_delivery_dispute(order.id, payload, self.admin, self.db, "admin")
        self.db.refresh(order)
        self.db.refresh(self.buyer_wallet)
        self.db.refresh(self.product)
        self.assertEqual(repeat["data"]["status"], "canceled")
        self.assertEqual(order.dispute_resolution, "refund")
        self.assertEqual(self.buyer_wallet.balance, Decimal("100.0000"))
        self.assertEqual(self.buyer_wallet.frozen, Decimal("0.0000"))
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "refund").count(), 1)
        self.assertEqual(self.db.query(MerchantSettlement).count(), 0)

    def test_gift_or_invite_card_hours_remain_nonwithdrawable_after_cancel(self):
        """A reserve/refund round trip must never turn rewards into cashable funds."""

        self.buyer_wallet.balance = Decimal("10")
        self.buyer_wallet.withdrawable_balance = Decimal("0")
        self.db.add(Ledger(
            user_id=self.buyer.id,
            wallet_id=self.buyer_wallet.id,
            type="invite_first_order_reward",
            direction="in",
            amount=Decimal("10"),
            balance_after=Decimal("10"),
            event_key="test:invite-reward-order-round-trip",
            remark="邀请奖励，仅限站内消费",
        ))
        self.db.commit()

        order = self._order()
        self.db.refresh(self.buyer_wallet)
        self.assertEqual(self.buyer_wallet.balance, Decimal("2.8000"))
        self.assertEqual(self.buyer_wallet.frozen, Decimal("7.2000"))
        self.assertEqual(self.buyer_wallet.withdrawable_balance, Decimal("0"))

        cancel_order(order.id, self.buyer, self.db, "android")
        self.db.refresh(self.buyer_wallet)
        self.assertEqual(self.buyer_wallet.balance, Decimal("10.0000"))
        self.assertEqual(self.buyer_wallet.frozen, Decimal("0.0000"))
        self.assertEqual(self.buyer_wallet.withdrawable_balance, Decimal("0"))

    def test_admin_release_and_retried_confirm_settle_only_once(self):
        order = self._deliver(self._order())
        dispute_delivery(
            order.id,
            OrderDisputeIn(reason="配置需要平台复核后再确认"),
            self.buyer,
            self.db,
            "web",
        )
        payload = OrderDisputeResolveIn(action="release", note="配置与商品描述一致，支持商家结算")
        resolve_delivery_dispute(order.id, payload, self.admin, self.db, "admin")
        resolve_delivery_dispute(order.id, payload, self.admin, self.db, "admin")
        confirm_delivery(order.id, self.buyer, self.db, "ios")

        self.db.refresh(order)
        self.db.refresh(self.seller_wallet)
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.dispute_resolution, "release")
        self.assertEqual(self.db.query(Asset).filter(Asset.order_id == order.id).count(), 1)
        self.assertEqual(self.db.query(MerchantSettlement).filter(
            MerchantSettlement.order_id == order.id,
        ).count(), 1)
        self.assertEqual(self.seller_wallet.balance, Decimal("6.480000"))
        self.assertEqual(self.seller_wallet.withdrawable_balance, Decimal("6.480000"))

    def test_all_reserved_fund_deadlines_are_bounded_and_idempotent(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        undelivered = self._order()
        undelivered.delivery_due_at = now - timedelta(seconds=1)
        self.db.commit()
        first = process_order_lifecycle(self.db, now=now)
        second = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(undelivered)
        self.assertEqual(first["delivery_refunded"], 1)
        self.assertEqual(second["delivery_refunded"], 0)
        self.assertEqual(undelivered.status, "canceled")

        delivered = self._deliver(self._order())
        delivered.confirmation_due_at = now - timedelta(seconds=1)
        self.db.commit()
        result = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(delivered)
        self.assertEqual(result["delivery_confirmed"], 1)
        self.assertEqual(delivered.status, "completed")

        # Expiry returns reserved inventory exactly once for the same order.
        delivered.end_at = now - timedelta(seconds=1)
        asset = self.db.query(Asset).filter(Asset.order_id == delivered.id).one()
        asset.end_at = delivered.end_at
        self.db.commit()
        expired = process_order_lifecycle(self.db, now=now)
        repeated = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(delivered)
        self.db.refresh(self.product)
        self.assertEqual(expired["expired"], 1)
        self.assertEqual(repeated["expired"], 0)
        self.assertEqual(delivered.status, "done")
        self.assertEqual(self.product.stock, 1)

    def test_unresolved_dispute_defaults_to_buyer_refund(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        order = self._deliver(self._order())
        dispute_delivery(
            order.id,
            OrderDisputeIn(reason="交付资源与约定配置不一致"),
            self.buyer,
            self.db,
            "android",
        )
        order.dispute_due_at = now - timedelta(seconds=1)
        self.db.commit()
        result = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(self.buyer_wallet)
        self.assertEqual(result["dispute_refunded"], 1)
        self.assertEqual(order.status, "canceled")
        self.assertEqual(order.dispute_resolution, "refund")
        self.assertEqual(self.buyer_wallet.balance, Decimal("100.0000"))
        self.assertEqual(self.buyer_wallet.frozen, Decimal("0.0000"))

    def test_expired_action_windows_cannot_race_the_lifecycle_job(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        undelivered = self._order()
        undelivered.delivery_due_at = now - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(BizError):
            self._deliver(undelivered)

        process_order_lifecycle(self.db, now=now)
        self.db.commit()
        delivered = self._deliver(self._order())
        delivered.confirmation_due_at = now - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(BizError):
            dispute_delivery(
                delivered.id,
                OrderDisputeIn(reason="已超过验收期限仍尝试发起争议"),
                self.buyer,
                self.db,
                "android",
            )

    def test_sqlite_concurrent_checkout_cannot_oversell_last_unit(self):
        with TemporaryDirectory() as tmp:
            database_path = f"{tmp}/checkout.db"
            engine = create_engine(
                f"sqlite:///{database_path}",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            seed = Session()
            buyer = User(phone="13900002011", username="并发买家", password="!")
            seller = User(
                phone="13900002012",
                username="并发商家",
                password="!",
                role="supplier",
                supplier_status="approved",
            )
            seed.add_all([buyer, seller])
            seed.flush()
            seed.add(Wallet(user_id=buyer.id, balance=Decimal("100"), frozen=Decimal("0")))
            supplier = Supplier(
                user_id=seller.id,
                company_name="并发测试商家",
                contact="商家",
                phone="13900002012",
                status="approved",
            )
            seed.add(supplier)
            seed.flush()
            product = Product(
                name="最后一台资源",
                gpu_model="RTX4090",
                memory="24GB",
                price=Decimal("0.01"),
                cycle=[30],
                stock=1,
                supplier_id=supplier.id,
                market_source="wod",
                status="on",
            )
            seed.add(product)
            seed.commit()
            buyer_id = buyer.id
            product_id = product.id
            seed.close()

            def checkout(suffix: str) -> str:
                db = Session()
                try:
                    current_buyer = db.get(User, buyer_id)
                    create_order(
                        OrderCreateIn(
                            product_id=product_id,
                            quantity=1,
                            cycle_days=30,
                            expected_unit_price_card_hours=Decimal("0.01"),
                            purchase_type="usage",
                            client_request_id=f"concurrent-checkout-{suffix}",
                        ),
                        current_buyer,
                        db,
                        "android",
                    )
                    return "ok"
                except BizError as exc:
                    return exc.msg
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = sorted(pool.map(checkout, ("0001", "0002")))

            check = Session()
            self.assertEqual(results.count("ok"), 1)
            self.assertEqual(check.query(Order).count(), 1)
            self.assertEqual(check.get(Product, product_id).stock, 0)
            checkout_wallet = check.query(Wallet).filter(Wallet.user_id == buyer_id).one()
            self.assertEqual(checkout_wallet.frozen, Decimal("7.2000"))
            check.close()
            engine.dispose()

    def test_stale_expiry_candidate_cannot_end_a_concurrently_renewed_order(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        order = self._deliver(self._order())
        confirm_delivery(order.id, self.buyer, self.db, "android")
        self.db.refresh(order)
        order.end_at = now + timedelta(days=30)
        self.db.commit()

        changed = _restore_expired_order_stock(order, self.db, now)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(self.product)
        self.assertFalse(changed)
        self.assertEqual(order.status, "completed")
        self.assertEqual(self.product.stock, 0)

    def test_legacy_expired_order_requires_stock_reconciliation_before_release(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        order = self._deliver(self._order())
        confirm_delivery(order.id, self.buyer, self.db, "android")
        self.db.refresh(order)
        order.end_at = now - timedelta(seconds=1)
        order.lifecycle_policy_version = None
        self.db.commit()

        result = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(self.product)
        self.assertEqual(result["expired"], 0)
        self.assertEqual(order.status, "completed")
        self.assertIsNone(order.stock_released_at)
        self.assertEqual(self.product.stock, 0)

    def test_invalid_financial_or_timeout_policy_fails_before_order_processing(self):
        settings.MERCHANT_SERVICE_FEE_BPS = 10001
        with self.assertRaises(MerchantSettlementError):
            assert_merchant_settlement_configuration_safe()

        settings.MERCHANT_SERVICE_FEE_BPS = 1000
        settings.ORDER_DELIVERY_TIMEOUT_HOURS = 0
        with self.assertRaises(MerchantSettlementError):
            assert_merchant_settlement_configuration_safe()

    def test_legacy_pending_order_requires_explicit_sla_migration_opt_in(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        order = self._order()
        order.delivery_due_at = None
        order.lifecycle_policy_version = None
        self.db.commit()

        untouched = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(order)
        self.assertEqual(untouched["deadline_backfilled"], 0)
        self.assertIsNone(order.delivery_due_at)
        self.assertIsNone(order.lifecycle_policy_version)

        settings.ORDER_LEGACY_PENDING_MIGRATION_ENABLED = True
        migrated = process_order_lifecycle(self.db, now=now)
        self.db.commit()
        self.db.refresh(order)
        self.assertEqual(migrated["deadline_backfilled"], 1)
        self.assertEqual(order.lifecycle_policy_version, "reserved-v1")
        self.assertEqual(order.delivery_due_at, now + timedelta(hours=24))


if __name__ == "__main__":
    unittest.main()
