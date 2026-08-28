import unittest
from datetime import datetime
from decimal import Decimal

from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import DEFAULT_SECRET_KEY, settings
from app.core.sensitive import (
    assert_sensitive_capabilities_secure,
    mask_bank_card,
    mask_id_card,
    protect,
    reveal,
    sensitive_capability_enabled,
    sensitive_security_errors,
)
from app.db.base import Base
from app.models import Asset, BankCard, Ledger, MarketSourceStatus, MerchantSettlement, Order, Product, Supplier, User, Wallet  # noqa: F401
from app.routers.bank_card import add_card
from app.routers.supplier import dashboard, store_page, supplier_withdraw
from app.routers.supplier import register
from app.routers.wallet import recharge
from app.routers.order import cancel_order, confirm_delivery, create_order, deliver_ssh
from app.routers.product import router as product_router
from app.schemas.bank_card import BankCardIn
from app.schemas.order import OrderCreateIn, OrderDeliverIn
from app.schemas.supplier import SupplierDeviceCreateIn, SupplierDeviceUpdateIn, SupplierRegisterIn
from app.schemas.wallet import RechargeIn
from app.services.wallet_balance import (
    historical_synthetic_revenue,
    historical_synthetic_rewards,
    spendable_wallet_balance,
)
from init_db import _ensure_user_wallets
from app.utils.response import BizError


class SecurityStateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="13900000001", username="安全测试用户", password="!", supplier_status="none")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id, balance=Decimal("100"), frozen=Decimal("0"))
        self.db.add(self.wallet)
        self.seller = User(phone="13900000002", username="已审核商家", password="!", role="supplier", supplier_status="approved")
        self.db.add(self.seller)
        self.db.flush()
        self.supplier = Supplier(
            user_id=self.seller.id,
            company_name="审核通过商家",
            contact="李四",
            phone="13900000002",
            status="approved",
        )
        self.db.add(self.supplier)
        self.db.flush()
        self.seller_wallet = Wallet(user_id=self.seller.id, balance=Decimal("10"), frozen=Decimal("0"))
        self.db.add(self.seller_wallet)
        self.db.commit()
        self.original_payment_state = settings.PAYMENT_SERVICE_ENABLED
        self.original_direct_trade = settings.DIRECT_TRADE_ENABLED
        settings.DIRECT_TRADE_ENABLED = True
        self.original_revenue_state = settings.REVENUE_SETTLEMENT_ENABLED
        self.original_reward_state = settings.REWARD_SERVICE_ENABLED
        self.original_closed_test_reward_state = settings.CLOSED_TEST_REWARD_ENABLED
        settings.CLOSED_TEST_REWARD_ENABLED = False
        self.original_fulfillment_users = settings.PLATFORM_FULFILLMENT_USER_IDS
        self.original_sensitive_settings = {
            name: getattr(settings, name)
            for name in (
                "SECRET_KEY", "SENSITIVE_DATA_KEY", "ID_OCR_ENABLED",
                "MANUAL_BANK_CARD_ENABLED", "MANUAL_PAYOUT_ENABLED",
            )
        }

    def tearDown(self):
        settings.PAYMENT_SERVICE_ENABLED = self.original_payment_state
        settings.DIRECT_TRADE_ENABLED = self.original_direct_trade
        settings.REVENUE_SETTLEMENT_ENABLED = self.original_revenue_state
        settings.REWARD_SERVICE_ENABLED = self.original_reward_state
        settings.CLOSED_TEST_REWARD_ENABLED = self.original_closed_test_reward_state
        settings.PLATFORM_FULFILLMENT_USER_IDS = self.original_fulfillment_users
        for name, value in self.original_sensitive_settings.items():
            setattr(settings, name, value)
        self.db.close()

    def test_sensitive_values_encrypt_and_mask(self):
        card = protect("6222021234567890")
        identity = protect("11010519491231002X")
        self.assertNotIn("6222021234567890", card)
        self.assertEqual(reveal(card), "6222021234567890")
        self.assertEqual(mask_bank_card(card), "6222 **** **** 7890")
        self.assertEqual(mask_id_card(identity), "1101************2X")

    def test_sensitive_capability_rejects_source_default_and_missing_key(self):
        settings.SECRET_KEY = DEFAULT_SECRET_KEY
        settings.SENSITIVE_DATA_KEY = ""
        settings.ID_OCR_ENABLED = True
        settings.MANUAL_BANK_CARD_ENABLED = False
        settings.MANUAL_PAYOUT_ENABLED = False

        self.assertIn("default_secret_key", sensitive_security_errors())
        self.assertIn("missing_sensitive_data_key", sensitive_security_errors())
        self.assertFalse(sensitive_capability_enabled(True))
        with self.assertRaisesRegex(RuntimeError, "ID_OCR_ENABLED"):
            assert_sensitive_capabilities_secure()

    def test_sensitive_capability_accepts_independent_fernet_key(self):
        settings.SECRET_KEY = "unit-test-sensitive-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        settings.ID_OCR_ENABLED = False
        settings.MANUAL_BANK_CARD_ENABLED = True
        settings.MANUAL_PAYOUT_ENABLED = True

        self.assertEqual(sensitive_security_errors(), ())
        self.assertTrue(sensitive_capability_enabled(True))
        self.assertIsNone(assert_sensitive_capabilities_secure())

    def test_public_product_catalog_has_no_unauthenticated_write_route(self):
        root_methods = {
            method
            for route in product_router.routes
            if getattr(route, "path", "") == "/api/products"
            for method in (getattr(route, "methods", set()) or set())
        }
        self.assertNotIn("POST", root_methods)

    def test_disabled_payment_never_mutates_balance(self):
        settings.PAYMENT_SERVICE_ENABLED = False
        with self.assertRaises(BizError):
            recharge(RechargeIn(amount=10), self.user, self.db)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("100"))

    def test_missing_legacy_wallet_is_restored_with_zero_credit(self):
        legacy = User(phone="13900000009", username="旧测试账号", password="!")
        self.db.add(legacy)
        self.db.commit()
        self.assertEqual(_ensure_user_wallets(self.db), 1)
        wallet = self.db.query(Wallet).filter(Wallet.user_id == legacy.id).one()
        self.assertEqual(wallet.balance, Decimal("0.0000"))
        self.assertEqual(wallet.frozen, Decimal("0.0000"))
        self.assertEqual(_ensure_user_wallets(self.db), 0)

    def test_supplier_application_stays_pending(self):
        result = register(SupplierRegisterIn(
            company_name="测试算力服务商",
            contact="张三",
            phone="13900000001",
            region="上海",
            desc="审核测试",
        ), self.user, self.db)
        supplier = self.db.query(Supplier).filter(Supplier.user_id == self.user.id).one()
        self.db.refresh(self.user)
        self.assertEqual(result["data"]["status"], "pending")
        self.assertEqual(supplier.status, "pending")
        self.assertEqual(self.user.supplier_status, "pending")

    def test_order_reserves_and_cancel_restores_stock(self):
        product = Product(
            name="RTX 4090 测试资源",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.01"),
            cycle=[30],
            stock=3,
            supplier_id=self.supplier.id,
            status="on",
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        result = create_order(OrderCreateIn(
            product_id=product.id,
            quantity=2,
            cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.01"),
            purchase_type="usage",
        ), self.user, self.db)
        self.db.refresh(product)
        self.assertEqual(product.stock, 1)
        cancel_order(result["data"]["id"], self.user, self.db)
        self.db.refresh(product)
        self.db.refresh(self.wallet)
        self.assertEqual(product.stock, 3)
        self.assertEqual(self.wallet.balance, Decimal("100"))
        self.assertEqual(self.wallet.frozen, Decimal("0"))

    def test_confirm_delivery_conserves_funds_and_settles_merchant_income(self):
        product = Product(
            name="RTX 4090 交付测试", gpu_model="RTX4090", memory="24GB",
            price=Decimal("0.01"), cycle=[30], stock=2,
            supplier_id=self.supplier.id, status="on",
        )
        self.db.add(product)
        self.db.commit()
        result = create_order(OrderCreateIn(
            product_id=product.id, quantity=2, cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.01"), purchase_type="usage",
        ), self.user, self.db)
        order_id = result["data"]["id"]
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("85.6000"))
        self.assertEqual(self.wallet.frozen, Decimal("14.4000"))
        entries = self.db.query(Ledger).filter(Ledger.ref_order_id == order_id).all()
        self.assertEqual([(entry.type, entry.amount) for entry in entries], [("freeze", Decimal("14.4000"))])

        deliver_ssh(
            order_id,
            OrderDeliverIn(ssh_info="ssh test@example.com -p 22"),
            self.seller,
            self.db,
        )
        confirm_delivery(order_id, self.user, self.db)
        self.db.refresh(self.wallet)
        self.db.refresh(self.seller_wallet)
        self.assertEqual(self.wallet.balance, Decimal("85.6000"))
        self.assertEqual(self.wallet.frozen, Decimal("0.0000"))
        entries = self.db.query(Ledger).filter(Ledger.ref_order_id == order_id).order_by(Ledger.id).all()
        self.assertEqual([entry.type for entry in entries], ["freeze", "pay", "merchant_sale_income"])
        self.assertEqual(entries[1].direction, "internal")
        settlement = self.db.query(MerchantSettlement).filter(
            MerchantSettlement.order_id == order_id,
        ).one()
        self.assertEqual(settlement.gross_amount, Decimal("14.400000"))
        self.assertEqual(settlement.service_fee_amount, Decimal("1.440000"))
        self.assertEqual(settlement.net_amount, Decimal("12.960000"))
        self.assertEqual(settlement.gross_amount, settlement.service_fee_amount + settlement.net_amount)
        self.assertEqual(self.seller_wallet.balance, Decimal("22.960000"))
        self.assertEqual(self.seller_wallet.withdrawable_balance, Decimal("12.960000"))
        self.assertEqual(spendable_wallet_balance(self.seller_wallet, self.db), Decimal("10.000000"))
        self.assertFalse(self.db.query(Ledger).filter(Ledger.ref_order_id == order_id, Ledger.type == "fee").count())
        created_asset = self.db.query(Asset).filter(Asset.order_id == order_id).one()
        self.assertEqual(Decimal(str(created_asset.daily_rate)), Decimal("0.000000"))
        self.assertIsNone(created_asset.rebate_status)
        self.assertFalse(self.db.query(Ledger).filter(
            Ledger.type.in_(["rebate", "supplier_rebate", "invite_reward"])
        ).count())

    def test_delivered_ssh_order_cannot_be_canceled(self):
        product = Product(
            name="交付后不可取消", gpu_model="A800", memory="80GB",
            price=Decimal("0.01"), cycle=[30], stock=1,
            supplier_id=self.supplier.id, status="on",
        )
        self.db.add(product)
        self.db.commit()
        result = create_order(OrderCreateIn(
            product_id=product.id,
            cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.01"),
        ), self.user, self.db)
        deliver_ssh(
            result["data"]["id"],
            OrderDeliverIn(ssh_info="ssh ubuntu@192.0.2.10 -p 22"),
            self.seller,
            self.db,
        )
        with self.assertRaises(BizError):
            cancel_order(result["data"]["id"], self.user, self.db)

    def test_live_external_usage_reserves_funds_and_holding_is_disabled(self):
        now = datetime.now()
        self.db.add(MarketSourceStatus(
            source="kai", enabled=True, status="ok", refresh_seconds=300,
            sample_count=1, last_attempt_at=now, last_success_at=now,
        ))
        external = Product(
            name="KAI RTX 4090", gpu_model="RTX4090", memory="24GB",
            price=Decimal("0.1002"), source_price=Decimal("0.1002"), source_currency="CNY",
            price_updated_at=now, cycle=[], stock=9, status="on",
            market_source="kai", external_product_id="security-kai-4090",
            # Even malformed legacy association data must not turn a KAI
            # self-operated order into merchant proceeds.
            supplier_id=self.supplier.id,
            source_max_configurable_quantity=9, platform_stock_cap=9,
        )
        local = Product(
            name="WOD 使用资源", gpu_model="RTX4090", memory="24GB",
            price=Decimal("0.01"), cycle=[30], stock=1,
            supplier_id=self.supplier.id, status="on",
        )
        self.db.add_all([external, local])
        self.db.commit()
        settings.PLATFORM_FULFILLMENT_USER_IDS = str(self.seller.id)
        external_result = create_order(OrderCreateIn(
            product_id=external.id, hours=72, purchase_type="usage",
            client_request_id="external-usage-0001",
        ), self.user, self.db)
        with self.assertRaises(BizError):
            create_order(OrderCreateIn(
                product_id=local.id, cycle_days=30, purchase_type="holding",
                expected_unit_price_card_hours=Decimal("0.01"),
                client_request_id="local-holding-0001",
            ), self.user, self.db)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("92.8000"))
        self.assertEqual(self.wallet.frozen, Decimal("7.2000"))
        self.assertEqual(self.db.query(Asset).count(), 0)
        self.assertIsNone(external_result["data"]["ssh_info"])

        with self.assertRaises(BizError):
            deliver_ssh(
                external_result["data"]["id"],
                OrderDeliverIn(ssh_info="pending credentials"),
                self.seller,
                self.db,
            )
        deliver_ssh(
            external_result["data"]["id"],
            OrderDeliverIn(ssh_info="ssh ubuntu@198.51.100.20 -p 22"),
            self.seller,
            self.db,
        )
        confirm_delivery(external_result["data"]["id"], self.user, self.db)
        external_asset = self.db.query(Asset).filter(
            Asset.order_id == external_result["data"]["id"]
        ).one()
        self.assertEqual(external_asset.purchase_type, "usage")
        self.assertEqual(Decimal(str(external_asset.daily_rate)), Decimal("0.000000"))
        self.assertEqual(self.db.query(MerchantSettlement).filter(
            MerchantSettlement.order_id == external_result["data"]["id"],
        ).count(), 0)
        self.db.refresh(self.seller_wallet)
        self.assertEqual(self.seller_wallet.balance, Decimal("10"))
        self.assertEqual(self.seller_wallet.withdrawable_balance, Decimal("0"))

    def test_order_client_request_id_is_idempotent(self):
        product = Product(
            name="幂等下单测试", gpu_model="A800", memory="80GB",
            price=Decimal("0.01"), cycle=[30], stock=3,
            supplier_id=self.supplier.id, status="on",
        )
        self.db.add(product)
        self.db.commit()
        payload = OrderCreateIn(
            product_id=product.id, quantity=2, cycle_days=30,
            expected_unit_price_card_hours=Decimal("0.01"),
            purchase_type="usage", client_request_id="idempotent-order-0001",
        )
        first = create_order(payload, self.user, self.db)
        second = create_order(payload, self.user, self.db)
        self.db.refresh(self.wallet)
        self.db.refresh(product)
        self.assertEqual(first["data"]["id"], second["data"]["id"])
        self.assertEqual(self.db.query(Order).count(), 1)
        self.assertEqual(product.stock, 1)
        self.assertEqual(self.wallet.balance, Decimal("85.6000"))
        self.assertEqual(self.wallet.frozen, Decimal("14.4000"))

    def test_disabled_supplier_withdrawal_and_bank_binding_do_not_mutate(self):
        settings.PAYMENT_SERVICE_ENABLED = False
        with self.assertRaises(BizError):
            supplier_withdraw({"amount": 1}, self.seller, self.db)
        with self.assertRaises(BizError):
            add_card(BankCardIn(
                bank_name="测试银行", card_number="6222021234567890",
                holder="李四", phone="13900000002",
            ), self.seller, self.db)
        self.db.refresh(self.seller_wallet)
        self.assertEqual(self.seller_wallet.balance, Decimal("10"))
        self.assertEqual(self.db.query(BankCard).filter(BankCard.user_id == self.seller.id).count(), 0)

    def test_zero_stock_cannot_be_purchased(self):
        product = Product(
            name="无库存资源",
            gpu_model="A800",
            memory="80GB",
            price=Decimal("0.01"),
            cycle=[30],
            stock=0,
            supplier_id=self.supplier.id,
            status="on",
        )
        self.db.add(product)
        self.db.commit()
        with self.assertRaises(BizError):
            create_order(OrderCreateIn(
                product_id=product.id,
                quantity=1,
                cycle_days=30,
                expected_unit_price_card_hours=Decimal("0.01"),
            ), self.user, self.db)

    def test_supplier_device_payload_rejects_invalid_price_stock_and_empty_update(self):
        with self.assertRaises(ValidationError):
            SupplierDeviceCreateIn(name="A800", gpu_model="A800", price=0, stock=1)
        with self.assertRaises(ValidationError):
            SupplierDeviceCreateIn(name="A800", gpu_model="A800", price=1, stock=-1)
        with self.assertRaises(ValidationError):
            SupplierDeviceUpdateIn()

    def test_empty_supplier_dashboard_does_not_invent_a_product_or_revenue(self):
        data = dashboard(self.seller, self.db)["data"]
        self.assertEqual(data["product_count"], 0)
        self.assertEqual(data["total_stock"], 0)
        self.assertEqual(data["today_revenue"], 0)
        self.assertEqual(data["total_revenue"], 0)

    def test_public_supplier_store_masks_phone_but_keeps_response_shape(self):
        product = Product(
            name="商家公开资源", gpu_model="RTX4090", memory="24GB",
            price=Decimal("1"), stock=1, supplier_id=self.supplier.id, status="on",
        )
        self.db.add(product)
        self.db.commit()
        data = store_page(self.supplier.id, self.db)["data"]["supplier"]
        self.assertEqual(data["phone"], "139****0002")
        self.assertNotIn("13900000002", str(data))
        self.assertEqual(data["company_name"], "审核通过商家")
        products = store_page(self.supplier.id, self.db)["data"]["products"]
        self.assertTrue(products[0]["purchasable"])

    def test_legacy_test_returns_and_rewards_are_not_spendable(self):
        settings.REVENUE_SETTLEMENT_ENABLED = False
        settings.REWARD_SERVICE_ENABLED = False
        entries = [
            ("revenue", Decimal("10")),
            ("rebate", Decimal("4")),
            ("supplier_rebate", Decimal("3")),
            ("invite_reward", Decimal("3")),
        ]
        self.wallet.balance = Decimal("120")
        for ledger_type, amount in entries:
            self.db.add(Ledger(
                user_id=self.user.id,
                wallet_id=self.wallet.id,
                type=ledger_type,
                direction="in",
                amount=amount,
                balance_after=self.wallet.balance,
                remark="legacy test credit",
            ))
        self.db.commit()
        self.assertEqual(historical_synthetic_revenue(self.user.id, self.db), Decimal("10.0000"))
        self.assertEqual(historical_synthetic_rewards(self.user.id, self.db), Decimal("10.0000"))
        self.assertEqual(spendable_wallet_balance(self.wallet, self.db), Decimal("100.0000"))


if __name__ == "__main__":
    unittest.main()
