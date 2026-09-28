import unittest
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import Coupon, CouponCampaign, Ledger, Order, Product, Supplier, User, Wallet  # noqa: F401
from app.routers.order import cancel_order, create_order
from app.schemas.coupon import CouponCampaignCreateIn
from app.schemas.order import OrderCreateIn
from app.services.coupon_service import (
    claim_coupon_for_order,
    create_campaign,
    effective_campaign_status,
    redeem_code,
    update_campaign_status,
    utc_now,
)
from app.utils.response import BizError


class CouponWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.original = {
            name: getattr(settings, name)
            for name in (
                "DIRECT_TRADE_ENABLED",
                "CONSUMER_REWARD_ENABLED",
                "SUPPLIER_REWARD_ENABLED",
                "INVITE_REWARD_ENABLED",
                "REWARD_SETTLEMENT_ENABLED",
                "SECRET_KEY",
            )
        }
        settings.DIRECT_TRADE_ENABLED = True
        settings.CONSUMER_REWARD_ENABLED = False
        settings.SUPPLIER_REWARD_ENABLED = False
        settings.INVITE_REWARD_ENABLED = False
        settings.REWARD_SETTLEMENT_ENABLED = False
        settings.SECRET_KEY = "coupon-workflow-unit-test-secret"

        self.buyer = User(phone="13900009001", username="兑换券买家", password="!")
        self.other = User(phone="13900009002", username="第二位买家", password="!")
        self.seller = User(
            phone="13900009003", username="兑换券商家", password="!",
            role="supplier", supplier_status="approved",
        )
        self.admin = User(phone="13900009004", username="兑换券管理员", password="!", role="admin")
        self.db.add_all([self.buyer, self.other, self.seller, self.admin])
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.buyer.id,
            balance=Decimal("10"),
            frozen=Decimal("0"),
            promotional_balance=Decimal("0"),
            promotional_frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
        )
        self.db.add(self.wallet)
        supplier = Supplier(
            user_id=self.seller.id,
            company_name="兑换券测试商家",
            contact="商家",
            phone="13900009003",
            status="approved",
        )
        self.db.add(supplier)
        self.db.flush()
        self.product = Product(
            name="兑换券流程测试商品",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.01"),
            cycle=[30],
            stock=2,
            supplier_id=supplier.id,
            market_source="wod",
            status="on",
        )
        self.db.add(self.product)
        self.db.commit()

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    def _campaign(self, *, code="KAI-TEST-2026-COUPON", limit=1):
        return create_campaign(
            self.db,
            data=CouponCampaignCreateIn(
                name="满 5 减 2 卡时券",
                amount=Decimal("2"),
                min_amount=Decimal("5"),
                max_redemptions=limit,
                coupon_ttl_days=30,
                expires_at=utc_now() + timedelta(days=60),
                code=code,
            ),
            actor_user_id=self.admin.id,
            platform="web",
        )

    def test_campaign_stores_only_hash_and_enforces_account_and_total_limits(self):
        campaign, plaintext = self._campaign()
        self.assertEqual(plaintext, "KAI-TEST-2026-COUPON")
        self.assertNotIn("TEST2026COUPON", campaign.code_hash)
        self.assertEqual(campaign.code_hint, "****UPON")
        coupon = redeem_code(
            self.db, user_id=self.buyer.id, code=plaintext, platform="android"
        )
        self.assertEqual(coupon.status, "available")
        self.assertEqual(coupon.created_platform, "android")
        with self.assertRaises(BizError):
            redeem_code(self.db, user_id=self.buyer.id, code=plaintext, platform="ios")
        with self.assertRaises(BizError):
            redeem_code(self.db, user_id=self.other.id, code=plaintext, platform="ios")
        self.db.refresh(campaign)
        self.assertEqual(campaign.redeemed_count, 1)
        self.assertEqual(effective_campaign_status(campaign), "exhausted")
        updated = update_campaign_status(
            self.db,
            campaign_id=campaign.id,
            status="disabled",
            expected_version=campaign.version,
            actor_user_id=self.admin.id,
        )
        self.assertEqual(updated.status, "disabled")
        self.assertEqual(updated.last_modified_by, self.admin.id)

    def test_coupon_discount_is_atomic_and_cancel_restores_wallet_and_coupon(self):
        _campaign, plaintext = self._campaign()
        coupon = redeem_code(
            self.db, user_id=self.buyer.id, code=plaintext, platform="android"
        )
        result = create_order(
            OrderCreateIn(
                product_id=self.product.id,
                quantity=1,
                cycle_days=30,
                expected_unit_price_card_hours=Decimal("0.01"),
                purchase_type="usage",
                coupon_id=coupon.id,
                client_request_id="coupon-order-request-0001",
            ),
            self.buyer,
            self.db,
            "android",
        )
        order = self.db.get(Order, result["data"]["id"])
        self.db.refresh(self.wallet)
        self.db.refresh(coupon)
        self.assertEqual(order.amount, Decimal("7.2000"))
        self.assertEqual(order.coupon_discount, Decimal("2.000000"))
        self.assertEqual(result["data"]["payable_amount_card_hours"], 5.2)
        self.assertEqual(self.wallet.balance, Decimal("4.800000"))
        self.assertEqual(self.wallet.frozen, Decimal("7.200000"))
        self.assertEqual(self.wallet.promotional_frozen, Decimal("2.000000"))
        self.assertEqual(coupon.status, "used")
        self.assertEqual(coupon.used_order_id, order.id)

        cancel_order(order.id, self.buyer, self.db, "ios")
        self.db.refresh(self.wallet)
        self.db.refresh(coupon)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))
        self.assertEqual(self.wallet.frozen, Decimal("0.000000"))
        self.assertEqual(self.wallet.promotional_balance, Decimal("0.000000"))
        self.assertEqual(self.wallet.promotional_frozen, Decimal("0.000000"))
        self.assertEqual(coupon.status, "available")
        self.assertIsNone(coupon.used_order_id)
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "coupon_credit").count(), 1)
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "coupon_restore").count(), 1)

    def test_holding_purchase_cannot_claim_coupon(self):
        _campaign, plaintext = self._campaign()
        coupon = redeem_code(
            self.db, user_id=self.buyer.id, code=plaintext, platform="web"
        )
        with self.assertRaises(BizError):
            claim_coupon_for_order(
                self.db,
                coupon_id=coupon.id,
                user_id=self.buyer.id,
                product_id=self.product.id,
                purchase_type="holding",
                gross_amount=Decimal("7.2"),
            )


if __name__ == "__main__":
    unittest.main()
