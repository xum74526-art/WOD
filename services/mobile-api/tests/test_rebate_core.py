import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import Asset, Ledger, Order, Product, Supplier, User, Wallet  # noqa: F401
from app.models.invite import InviteCode, InviteRecord
from app.routers.invite import process_first_order_reward, summary
from app.routers.order import confirm_delivery, create_order, deliver_ssh
from app.routers.wallet import WithdrawInV2, ledger_list, withdraw
from app.schemas.order import OrderCreateIn
from app.services.rebate_settle import get_rebate_summary, settle_rebates
from app.services.supplier_rebate import get_supplier_rebate_summary, process_supplier_rebate
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
        settings.REWARD_SERVICE_ENABLED = False
        settings.CLOSED_TEST_REWARD_ENABLED = True

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
        self.db.close()

    def _complete_order(self) -> int:
        result = create_order(OrderCreateIn(
            product_id=self.product.id,
            quantity=1,
            cycle_days=30,
            purchase_type="usage",
            client_request_id="rebate-order-0001",
        ), self.buyer, self.db)
        order_id = result["data"]["id"]
        deliver_ssh(order_id, {"ssh_info": "ssh user@192.0.2.20 -p 22"}, self.seller, self.db)
        confirm_delivery(order_id, self.buyer, self.db)
        return order_id

    def test_confirmed_order_drives_all_three_reward_views(self):
        order_id = self._complete_order()
        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        self.assertEqual(asset.rebate_status, "pending")
        self.assertEqual(Decimal(str(asset.rebate_amount)), Decimal("0.43"))

        consumer = get_rebate_summary(self.buyer.id, self.db)
        merchant = get_supplier_rebate_summary(self.seller.id, self.db)
        invite = summary(self.inviter, self.db)["data"]
        self.assertEqual(consumer["reward_mode"], "test_card_hours")
        self.assertEqual(consumer["month_spent"], 14.4)
        self.assertEqual(consumer["pending_rebate"], 0.43)
        self.assertEqual(merchant["month_sales"], 14.4)
        self.assertEqual(merchant["month_rebated"], 0.07)
        self.assertEqual(invite["current_tier"], "15%")
        self.assertEqual(invite["total_reward"], 2.16)

    def test_reward_credit_is_idempotent_and_matches_ledger(self):
        order_id = self._complete_order()
        self.assertEqual(process_first_order_reward(self.buyer.id, order_id, self.db), Decimal("0"))
        self.assertEqual(process_supplier_rebate(self.seller.id, order_id, self.db), Decimal("0"))

        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        asset.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.db.commit()
        self.assertEqual(settle_rebates(self.db), 1)
        self.db.commit()
        self.assertEqual(settle_rebates(self.db), 0)
        self.db.commit()

        rewards = self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type.in_(["test_rebate", "test_supplier", "test_invite"]),
        ).all()
        self.assertEqual(len(rewards), 3)
        self.assertEqual(sum((row.amount for row in rewards), Decimal("0")), Decimal("2.6600"))
        self.assertEqual(
            self.db.query(Ledger).filter(
                Ledger.ref_order_id == order_id,
                Ledger.type == "test_rebate",
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

    def test_unverified_relationship_is_visible_but_never_rewarded(self):
        relation = self.db.query(InviteRecord).filter(InviteRecord.invitee_id == self.buyer.id).one()
        self.buyer.phone_bound = False
        relation.status = "unverified"
        self.db.commit()
        order_id = self._complete_order()
        self.assertEqual(self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type == "test_invite",
        ).count(), 0)
        self.db.refresh(relation)
        self.assertEqual(relation.status, "unverified")

    def test_quantity_is_applied_once_to_rebate_value(self):
        result = create_order(OrderCreateIn(
            product_id=self.product.id,
            quantity=2,
            cycle_days=30,
            purchase_type="usage",
            client_request_id="rebate-order-quantity-0001",
        ), self.buyer, self.db)
        order_id = result["data"]["id"]
        deliver_ssh(order_id, {"ssh_info": "ssh user@192.0.2.21 -p 22"}, self.seller, self.db)
        confirm_delivery(order_id, self.buyer, self.db)
        asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        self.assertEqual(asset.quantity, 2)
        self.assertEqual(Decimal(str(asset.value)), Decimal("14.4000"))
        self.assertEqual(Decimal(str(asset.rebate_amount)), Decimal("0.86"))
        asset.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.db.commit()
        self.assertEqual(settle_rebates(self.db), 1)
        self.db.commit()
        ledger = self.db.query(Ledger).filter(
            Ledger.ref_order_id == order_id,
            Ledger.type == "test_rebate",
        ).one()
        self.assertEqual(ledger.amount, Decimal("0.8600"))

    def test_closed_test_card_hours_are_never_withdrawable(self):
        settings.PAYMENT_SERVICE_ENABLED = True
        with self.assertRaisesRegex(Exception, "封闭测试卡时"):
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
                purchase_type="usage",
            ), self.seller, self.db)
        self.assertEqual(self.db.query(Order).filter(Order.user_id == self.seller.id).count(), 0)


if __name__ == "__main__":
    unittest.main()
