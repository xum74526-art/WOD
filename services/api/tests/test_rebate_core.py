import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import Asset, Ledger, Order, Product, RewardAccrual, Supplier, User, Wallet  # noqa: F401
from app.models.invite import InviteCode, InviteRecord
from app.routers.invite import process_first_order_reward, summary
from app.routers.order import confirm_delivery, create_order, deliver_ssh
from app.routers.wallet import WithdrawInV2, ledger_list, withdraw
from app.schemas.order import OrderCreateIn, OrderDeliverIn
from app.services.reward_entitlements import (
    create_supplier_order_accrual,
    get_asset_consumer_reward,
    get_consumer_summary,
    get_supplier_summary,
    settle_reward_entitlements,
)
from app.utils.response import BizError


class RebateCoreTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.original_live = settings.REWARD_SERVICE_ENABLED
        self.original_test = settings.CLOSED_TEST_REWARD_ENABLED
        self.original_payment = settings.PAYMENT_SERVICE_ENABLED
        self.original_direct_trade = settings.DIRECT_TRADE_ENABLED
        self.original_revenue_settlement = settings.REVENUE_SETTLEMENT_ENABLED
        self.original_consumer = settings.CONSUMER_REWARD_ENABLED
        self.original_supplier = settings.SUPPLIER_REWARD_ENABLED
        self.original_invite = settings.INVITE_REWARD_ENABLED
        self.original_reward_settlement = settings.REWARD_SETTLEMENT_ENABLED
        self.original_secret = settings.SECRET_KEY
        self.original_sensitive_key = settings.SENSITIVE_DATA_KEY
        settings.REWARD_SERVICE_ENABLED = False
        settings.CLOSED_TEST_REWARD_ENABLED = False
        settings.CONSUMER_REWARD_ENABLED = True
        settings.SUPPLIER_REWARD_ENABLED = True
        settings.INVITE_REWARD_ENABLED = True
        settings.REWARD_SETTLEMENT_ENABLED = True
        settings.DIRECT_TRADE_ENABLED = True
        settings.REVENUE_SETTLEMENT_ENABLED = False
        settings.SECRET_KEY = "unit-test-rebate-core-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")

        self.inviter = User(
            phone="13900000051", username="邀请人", password="!", phone_bound=True,
        )
        self.buyer = User(
            phone="13900000052", username="买家", password="!", phone_bound=True,
        )
        self.seller = User(
            phone="13900000053", username="商家", password="!", phone_bound=True,
            role="supplier", supplier_status="approved",
        )
        self.db.add_all([self.inviter, self.buyer, self.seller])
        self.db.flush()
        self.buyer.invited_by = self.inviter.id
        self.db.add_all([
            Wallet(user_id=self.inviter.id, balance=Decimal("0"), frozen=Decimal("0")),
            Wallet(user_id=self.buyer.id, balance=Decimal("100"), frozen=Decimal("0")),
            Wallet(user_id=self.seller.id, balance=Decimal("0"), frozen=Decimal("0")),
            InviteCode(user_id=self.inviter.id, code="WODREBATE", invited_count=1),
            InviteRecord(
                inviter_id=self.inviter.id,
                invitee_id=self.buyer.id,
                invitee_phone="139****0052",
                status="registered",
                reward_amount=0,
            ),
        ])
        self.supplier = Supplier(
            user_id=self.seller.id,
            company_name="测试商家",
            contact="商家",
            phone="13900000053",
            status="approved",
        )
        self.db.add(self.supplier)
        self.db.flush()
        self.product = Product(
            name="RTX 4090 返佣测试",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.02"),
            cycle=[30],
            stock=2,
            supplier_id=self.supplier.id,
            status="on",
        )
        self.db.add(self.product)
        self.db.commit()

    def tearDown(self):
        settings.REWARD_SERVICE_ENABLED = self.original_live
        settings.CLOSED_TEST_REWARD_ENABLED = self.original_test
        settings.PAYMENT_SERVICE_ENABLED = self.original_payment
        settings.DIRECT_TRADE_ENABLED = self.original_direct_trade
        settings.REVENUE_SETTLEMENT_ENABLED = self.original_revenue_settlement
        settings.CONSUMER_REWARD_ENABLED = self.original_consumer
        settings.SUPPLIER_REWARD_ENABLED = self.original_supplier
        settings.INVITE_REWARD_ENABLED = self.original_invite
        settings.REWARD_SETTLEMENT_ENABLED = self.original_reward_settlement
        settings.SECRET_KEY = self.original_secret
        settings.SENSITIVE_DATA_KEY = self.original_sensitive_key
        self.db.close()

    def _complete_order(self) -> int:
        result = create_order(OrderCreateIn(
            product_id=self.product.id,
            quantity=1,
            cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.02"),
            purchase_type="usage",
            client_request_id="rebate-order-0001",
        ), self.buyer, self.db)
        order_id = result["data"]["id"]
        deliver_ssh(
            order_id,
            OrderDeliverIn(ssh_info="ssh user@192.0.2.20 -p 22"),
            self.seller,
            self.db,
        )
        confirm_delivery(order_id, self.buyer, self.db)
        return order_id

    def test_confirmed_order_drives_all_three_reward_views(self):
        order_id = self._complete_order()
        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        self.assertIsNone(asset.rebate_status)
        self.assertEqual(Decimal(str(asset.rebate_amount)), Decimal("0"))
        asset_reward = get_asset_consumer_reward(asset.id, self.db)
        self.assertEqual(asset_reward["rebate_status"], "pending")
        self.assertEqual(Decimal(str(asset_reward["rebate_amount"])), Decimal("0.43"))

        consumer = get_consumer_summary(self.buyer.id, self.db)
        merchant = get_supplier_summary(self.seller.id, self.db)
        invite = summary(self.inviter, self.db)["data"]
        self.assertEqual(consumer["reward_mode"], "live")
        self.assertEqual(consumer["month_spent"], 14.4)
        self.assertEqual(consumer["pending_rebate"], 0.43)
        self.assertEqual(consumer["minimum_order_amount"], 0.0)
        self.assertEqual(consumer["tiers"], [
            {"max_month_spent": 10000.0, "rate": 3, "rate_bps": 300},
            {"max_month_spent": 50000.0, "rate": 5, "rate_bps": 500},
            {"max_month_spent": 100000.0, "rate": 7, "rate_bps": 700},
            {"max_month_spent": None, "rate": 10, "rate_bps": 1000},
        ])
        self.assertEqual(merchant["month_sales"], 14.4)
        self.assertEqual(merchant["month_rebated"], 0.72)
        self.assertEqual(merchant["month_entitled"], 0.72)
        self.assertEqual(invite["current_tier"], "15%")
        self.assertEqual(invite["total_reward"], 2.16)

    def test_reward_credit_is_idempotent_and_matches_ledger(self):
        order_id = self._complete_order()
        self.assertEqual(process_first_order_reward(self.buyer.id, order_id, self.db), Decimal("0"))
        order = self.db.query(Order).filter(Order.id == order_id).one()
        self.assertIsNotNone(
            create_supplier_order_accrual(order, datetime.now(timezone.utc), self.db),
        )

        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        asset.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.db.query(RewardAccrual).filter(
            RewardAccrual.asset_id == asset.id,
        ).update({RewardAccrual.due_at: asset.end_at}, synchronize_session=False)
        self.db.commit()
        self.assertEqual(settle_reward_entitlements(self.db), 1)
        self.db.commit()
        self.assertEqual(settle_reward_entitlements(self.db), 0)
        self.db.commit()

        rewards = self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type.in_([
                "consumer_purchase_rebate",
                "supplier_sales_rebate",
                "invite_first_order_reward",
            ]),
        ).all()
        self.assertEqual(len(rewards), 3)
        self.assertEqual(sum((row.amount for row in rewards), Decimal("0")), Decimal("3.3100"))
        self.assertEqual(
            self.db.query(Ledger).filter(
                Ledger.ref_order_id == order_id,
                Ledger.type == "consumer_purchase_rebate",
            ).count(),
            1,
        )
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.assertEqual(buyer_wallet.frozen, Decimal("0.0000"))
        self.assertEqual(buyer_wallet.balance, Decimal("86.0300"))
        consumer_rows = ledger_list("rebate", 1, 20, self.buyer, self.db)["data"]["items"]
        supplier_rows = ledger_list("supplier_rebate", 1, 20, self.seller, self.db)["data"]["items"]
        invite_rows = ledger_list("invite_reward", 1, 20, self.inviter, self.db)["data"]["items"]
        self.assertEqual([row["type"] for row in consumer_rows], ["rebate"])
        self.assertEqual([row["type"] for row in supplier_rows], ["supplier_rebate"])
        self.assertEqual([row["type"] for row in invite_rows], ["invite_reward"])

    def test_legacy_ledger_rows_use_neutral_public_copy(self):
        wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.db.add_all([
            Ledger(
                user_id=self.buyer.id,
                wallet_id=wallet.id,
                type="revenue",
                direction="in",
                amount=Decimal("1"),
                balance_after=wallet.balance,
                remark="legacy revenue",
            ),
            Ledger(
                user_id=self.buyer.id,
                wallet_id=wallet.id,
                type="rebate",
                direction="in",
                amount=Decimal("2"),
                balance_after=wallet.balance,
                remark="legacy reward",
            ),
            Ledger(
                user_id=self.buyer.id,
                wallet_id=wallet.id,
                type="test_rebate",
                direction="in",
                amount=Decimal("3"),
                balance_after=wallet.balance,
                remark="legacy closed-test reward",
            ),
        ])
        self.db.commit()

        rows = ledger_list(None, 1, 20, self.buyer, self.db)["data"]["items"]
        remarks = {row["type"]: row["remark"] for row in rows}
        self.assertEqual(remarks["test_revenue"], "历史未结算收益（不计入当前可用余额）")
        self.assertEqual(remarks["test_reward"], "历史不可用奖励（不计入当前可用余额或权益）")
        self.assertEqual(sum(row["type"] == "test_reward" for row in rows), 2)
        self.assertNotIn("测试", "".join(remarks.values()))

    def test_unverified_relationship_is_visible_but_never_rewarded(self):
        relation = self.db.query(InviteRecord).filter(InviteRecord.invitee_id == self.buyer.id).one()
        self.buyer.phone_bound = False
        relation.status = "unverified"
        self.db.commit()
        order_id = self._complete_order()
        self.assertEqual(self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type == "invite_first_order_reward",
        ).count(), 0)
        self.db.refresh(relation)
        self.assertEqual(relation.status, "unverified")

    def test_quantity_is_applied_once_to_rebate_value(self):
        result = create_order(OrderCreateIn(
            product_id=self.product.id,
            quantity=2,
            cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.02"),
            purchase_type="usage",
            client_request_id="rebate-order-quantity-0001",
        ), self.buyer, self.db)
        order_id = result["data"]["id"]
        deliver_ssh(
            order_id,
            OrderDeliverIn(ssh_info="ssh user@192.0.2.21 -p 22"),
            self.seller,
            self.db,
        )
        confirm_delivery(order_id, self.buyer, self.db)
        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        self.assertEqual(asset.quantity, 2)
        self.assertEqual(Decimal(str(asset.value)), Decimal("14.4000"))
        self.assertEqual(Decimal(str(asset.rebate_amount)), Decimal("0"))
        self.assertEqual(
            Decimal(str(get_asset_consumer_reward(asset.id, self.db)["rebate_amount"])),
            Decimal("0.86"),
        )
        asset.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.db.query(RewardAccrual).filter(
            RewardAccrual.asset_id == asset.id,
        ).update({RewardAccrual.due_at: asset.end_at}, synchronize_session=False)
        self.db.commit()
        self.assertEqual(settle_reward_entitlements(self.db), 1)
        self.db.commit()
        ledger = self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type == "consumer_purchase_rebate",
        ).one()
        self.assertEqual(ledger.amount, Decimal("0.8600"))

    def test_closed_test_card_hours_are_never_withdrawable(self):
        settings.PAYMENT_SERVICE_ENABLED = True
        with self.assertRaisesRegex(Exception, "旧版即时提现入口已停用"):
            withdraw(WithdrawInV2(amount=1, bank_card_id=1), self.inviter, self.db)

    def test_merchant_cannot_generate_rewards_by_buying_own_listing(self):
        seller_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.seller.id).one()
        seller_wallet.balance = Decimal("100")
        self.db.commit()
        with self.assertRaises(BizError):
            create_order(OrderCreateIn(
                product_id=self.product.id,
                quantity=1,
                cycle_days=30,
                expected_unit_price_card_hours=Decimal("0.02"),
                purchase_type="usage",
            ), self.seller, self.db)
        self.assertEqual(self.db.query(Order).filter(Order.user_id == self.seller.id).count(), 0)


if __name__ == "__main__":
    unittest.main()
