import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.sensitive import protect
from app.db.base import Base
from app.models import MerchantSettlement, Order, Product, Supplier, User, Wallet  # noqa: F401
from app.routers.admin import orders as admin_orders
from app.routers.order import confirm_delivery, create_order, deliver_ssh, renew_order
from app.routers.product import list_products
from app.routers.supplier import add_device, supplier_orders, update_device
from app.schemas.order import OrderCreateIn, OrderDeliverIn, OrderRenewIn
from app.schemas.supplier import SupplierDeviceCreateIn, SupplierDeviceUpdateIn
from app.utils.response import BizError
from init_db import _reconcile_supplier_completed_order_counts


class MerchantCommerceFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.original_settings = {
            name: getattr(settings, name)
            for name in (
                "CONSUMER_REWARD_ENABLED",
                "SUPPLIER_REWARD_ENABLED",
                "INVITE_REWARD_ENABLED",
                "REWARD_SETTLEMENT_ENABLED",
                "MERCHANT_SERVICE_FEE_BPS",
                "ORDER_DELIVERY_TIMEOUT_HOURS",
                "ORDER_CONFIRMATION_TIMEOUT_HOURS",
            )
        }
        settings.CONSUMER_REWARD_ENABLED = False
        settings.SUPPLIER_REWARD_ENABLED = False
        settings.INVITE_REWARD_ENABLED = False
        settings.REWARD_SETTLEMENT_ENABLED = False
        settings.MERCHANT_SERVICE_FEE_BPS = 1000
        settings.ORDER_DELIVERY_TIMEOUT_HOURS = 24
        settings.ORDER_CONFIRMATION_TIMEOUT_HOURS = 24

        self.buyer = User(
            username="交易闭环买家",
            phone="13900004001",
            password="!",
        )
        self.seller = User(
            username="交易闭环商家",
            phone="13900004002",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.other_seller = User(
            username="其他已审核商家",
            phone="13900004003",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.admin = User(
            username="交易闭环管理员",
            phone="13900004004",
            password="!",
            role="admin",
        )
        self.db.add_all([self.buyer, self.seller, self.other_seller, self.admin])
        self.db.flush()
        self.db.add_all([
            Wallet(user_id=self.buyer.id, balance=Decimal("1000"), frozen=Decimal("0")),
            Wallet(
                user_id=self.seller.id,
                balance=Decimal("0"),
                frozen=Decimal("0"),
                withdrawable_balance=Decimal("0"),
            ),
            Wallet(
                user_id=self.other_seller.id,
                balance=Decimal("0"),
                frozen=Decimal("0"),
                withdrawable_balance=Decimal("0"),
            ),
        ])
        self.supplier = Supplier(
            user_id=self.seller.id,
            company_name="真实算力商家",
            contact="商家联系人",
            phone=self.seller.phone,
            status="approved",
            rating=4.9,
        )
        self.other_supplier = Supplier(
            user_id=self.other_seller.id,
            company_name="其他算力商家",
            contact="其他联系人",
            phone=self.other_seller.phone,
            status="approved",
        )
        self.db.add_all([self.supplier, self.other_supplier])
        self.db.commit()

    def tearDown(self):
        for name, value in self.original_settings.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    def test_create_publish_purchase_deliver_confirm_and_settle(self):
        created = add_device(
            SupplierDeviceCreateIn(
                name="商家 RTX 5090 32GB",
                gpu_model="RTX5090",
                memory="32GB",
                cuda="12.8",
                price=Decimal("0.01"),
                stock=2,
                desc="商家自行申报的可交付算力",
                region_code="east_china",
                region_name="华东",
                city="上海",
            ),
            self.seller,
            self.db,
        )["data"]
        product = self.db.get(Product, created["id"])
        self.assertEqual(product.market_source, "wod")
        self.assertEqual(product.stock_semantics, "supplier_reported_inventory")

        catalog = list_products(
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
            page_size=20,
            db=self.db,
        )["data"]
        self.assertEqual(catalog["total"], 1)
        listing = catalog["items"][0]
        self.assertEqual(listing["seller_type"], "merchant")
        self.assertEqual(listing["seller_name"], "真实算力商家")
        self.assertEqual(listing["reported_stock"], 2)
        self.assertTrue(listing["purchasable"])

        created_order = create_order(
            OrderCreateIn(
                product_id=product.id,
                quantity=1,
                hours=24,
                expected_unit_price_card_hours=Decimal("0.01"),
                purchase_type="usage",
                client_request_id="merchant-flow-order-0001",
            ),
            self.buyer,
            self.db,
            "android",
        )["data"]
        order = self.db.get(Order, created_order["id"])
        self.assertEqual(order.status, "paid")
        self.assertEqual(product.stock, 1)
        self.assertEqual(created_order["seller_type"], "merchant")
        self.assertEqual(created_order["fulfillment_mode"], "merchant_manual")
        self.assertEqual(created_order["purchase_unit"], "hour")
        self.assertEqual(created_order["amount_card_hours"], 0.24)
        self.assertEqual(
            created_order["product_snapshot"]["confirmed_unit_price_card_hours"],
            "0.0100",
        )
        self.assertEqual(created_order["product_snapshot"]["seller_id"], self.supplier.id)
        self.assertEqual(created_order["product_snapshot"]["seller_type"], "merchant")

        merchant_queue = supplier_orders(None, self.seller, self.db)["data"]
        self.assertEqual(len(merchant_queue), 1)
        self.assertEqual(merchant_queue[0]["buyer_phone"], "139****4001")
        self.assertTrue(merchant_queue[0]["can_deliver"])

        with self.assertRaises(BizError) as unauthorized:
            deliver_ssh(
                order.id,
                OrderDeliverIn(ssh_info="ssh ubuntu@192.0.2.70 -p 22"),
                self.other_seller,
                self.db,
                "ios",
            )
        self.assertEqual(unauthorized.exception.status_code, 403)

        delivered = deliver_ssh(
            order.id,
            OrderDeliverIn(ssh_info="ssh ubuntu@192.0.2.70 -p 22"),
            self.seller,
            self.db,
            "android",
        )["data"]
        self.assertEqual(delivered["status"], "delivering")
        self.assertFalse(delivered["can_deliver"])
        self.assertTrue(delivered["can_confirm"])
        self.assertTrue(delivered["can_dispute"])

        completed = confirm_delivery(
            order.id,
            self.buyer,
            self.db,
            "android",
        )["data"]
        self.assertEqual(completed["status"], "completed")
        self.assertFalse(completed["can_renew"])
        settlement = self.db.query(MerchantSettlement).filter(
            MerchantSettlement.order_id == order.id,
        ).one()
        self.assertEqual(settlement.gross_amount, Decimal("0.240000"))
        self.assertEqual(settlement.net_amount, Decimal("0.216000"))
        seller_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.seller.id).one()
        self.assertEqual(seller_wallet.withdrawable_balance, Decimal("0.216000"))
        self.db.refresh(self.supplier)
        self.assertEqual(self.supplier.order_count, 1)

        with self.assertRaises(BizError) as disabled_renewal:
            renew_order(
                order.id,
                OrderRenewIn(
                    hours=12,
                    client_request_id="merchant-flow-renew-0001",
                ),
                self.buyer,
                self.db,
                "android",
            )
        self.assertEqual(disabled_renewal.exception.status_code, 409)
        self.assertIn("重新下单", disabled_renewal.exception.msg)
        self.assertEqual(self.db.query(MerchantSettlement).filter(
            MerchantSettlement.order_id == order.id,
            MerchantSettlement.source_type == "renewal",
        ).count(), 0)
        self.db.refresh(seller_wallet)
        self.assertEqual(seller_wallet.withdrawable_balance, Decimal("0.216000"))

        self.supplier.order_count = 99
        self.db.commit()
        _reconcile_supplier_completed_order_counts(self.engine)
        self.db.expire_all()
        self.assertEqual(self.db.get(Supplier, self.supplier.id).order_count, 1)

    def test_stale_expected_price_rejects_before_stock_or_wallet_reservation(self):
        created = add_device(
            SupplierDeviceCreateIn(
                name="改价竞态测试资源",
                gpu_model="RTX4090",
                memory="24GB",
                price=Decimal("0.0100"),
                stock=2,
            ),
            self.seller,
            self.db,
        )["data"]
        product = self.db.get(Product, created["id"])
        update_device(
            product.id,
            SupplierDeviceUpdateIn(price=Decimal("0.0200")),
            self.seller,
            self.db,
        )
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        original_balance = buyer_wallet.balance
        original_frozen = buyer_wallet.frozen

        with self.assertRaises(BizError) as stale_price:
            create_order(
                OrderCreateIn(
                    product_id=product.id,
                    quantity=1,
                    hours=24,
                    expected_unit_price_card_hours=Decimal("0.0100"),
                    client_request_id="merchant-stale-price-0001",
                ),
                self.buyer,
                self.db,
                "android",
            )
        self.assertEqual(stale_price.exception.status_code, 409)
        self.assertEqual(stale_price.exception.msg, "价格已更新，请刷新后重新确认")
        self.db.rollback()
        self.assertEqual(self.db.get(Product, product.id).stock, 2)
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.assertEqual(buyer_wallet.balance, original_balance)
        self.assertEqual(buyer_wallet.frozen, original_frozen)
        self.assertEqual(self.db.query(Order).count(), 0)

    def test_zero_amount_is_rejected_before_stock_or_wallet_reservation(self):
        product = Product(
            name="异常零价商家资源",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0"),
            cycle=[],
            stock=1,
            status="on",
            market_source="wod",
            supplier_id=self.supplier.id,
        )
        self.db.add(product)
        self.db.commit()
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        original_balance = buyer_wallet.balance

        with self.assertRaises(BizError) as invalid_amount:
            create_order(
                OrderCreateIn(
                    product_id=product.id,
                    quantity=1,
                    hours=1,
                    expected_unit_price_card_hours=Decimal("0"),
                    client_request_id="merchant-zero-amount-0001",
                ),
                self.buyer,
                self.db,
                "android",
            )
        self.assertEqual(invalid_amount.exception.status_code, 409)
        self.db.rollback()
        self.assertEqual(self.db.get(Product, product.id).stock, 1)
        buyer_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.buyer.id).one()
        self.assertEqual(buyer_wallet.balance, original_balance)
        self.assertEqual(buyer_wallet.frozen, Decimal("0"))
        self.assertEqual(self.db.query(Order).count(), 0)

    def test_admin_dispute_queue_contains_reason_deadline_and_seller_facts(self):
        product = Product(
            name="争议队列商家资源",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.02"),
            cycle=[],
            stock=1,
            status="on",
            market_source="wod",
            supplier_id=self.supplier.id,
        )
        self.db.add(product)
        self.db.flush()
        now = datetime.now()
        order = Order(
            order_no="WOD-DISPUTE-0001",
            user_id=self.buyer.id,
            product_id=product.id,
            quantity=1,
            purchase_hours=24,
            cycle_days=0,
            amount=Decimal("0.48"),
            status="disputed",
            purchase_type="usage",
            dispute_reason="交付资源配置与商品说明不一致",
            disputed_at=now,
            dispute_due_at=now + timedelta(hours=72),
            delivered_at=now - timedelta(hours=1),
            confirmation_due_at=now + timedelta(hours=23),
            ssh_info=protect("ssh ubuntu@192.0.2.90 -p 22"),
            product_snapshot={
                "product_name": "争议队列商家资源",
                "gpu_model": "RTX4090",
                "memory": "24GB",
                "confirmed_unit_price_card_hours": "0.0200",
                "seller_id": self.supplier.id,
                "seller_type": "merchant",
                "seller_name": "真实算力商家",
                "market_source": "wod",
            },
        )
        self.db.add(order)
        self.db.commit()

        data = admin_orders(
            platform=None,
            status="disputed",
            order_no=None,
            page=1,
            page_size=20,
            actor=self.admin,
            db=self.db,
        )["data"]
        self.assertEqual(data["total"], 1)
        item = data["items"][0]
        self.assertEqual(item["dispute_reason"], "交付资源配置与商品说明不一致")
        self.assertIsNotNone(item["disputed_at"])
        self.assertIsNotNone(item["dispute_due_at"])
        self.assertEqual(item["seller_type"], "merchant")
        self.assertEqual(item["seller_name"], "真实算力商家")
        self.assertEqual(item["fulfillment_mode"], "merchant_manual")
        self.assertIsNotNone(item["delivered_at"])
        self.assertIsNotNone(item["confirmation_due_at"])
        self.assertTrue(item["ssh_info_present"])
        self.assertEqual(len(item["ssh_info_fingerprint"]), 16)
        self.assertNotIn("ssh_info", item)
        self.assertEqual(
            item["product_snapshot"]["confirmed_unit_price_card_hours"],
            "0.0200",
        )

    def test_supplier_order_queue_does_not_silently_drop_the_fifty_first_order(self):
        product = Product(
            name="商家订单队列资源",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("0.01"),
            cycle=[],
            stock=100,
            status="on",
            market_source="wod",
            supplier_id=self.supplier.id,
        )
        self.db.add(product)
        self.db.flush()
        orders = [
            Order(
                order_no=f"WOD-QUEUE-{index:04d}",
                user_id=self.buyer.id,
                product_id=product.id,
                quantity=1,
                purchase_hours=1,
                cycle_days=0,
                amount=Decimal("0.01"),
                status="paid",
                purchase_type="usage",
            )
            for index in range(1, 52)
        ]
        self.db.add_all(orders)
        self.db.commit()

        queue = supplier_orders(None, self.seller, self.db)["data"]
        self.assertEqual(len(queue), 51)
        self.assertIn("WOD-QUEUE-0051", {item["order_no"] for item in queue})

    def test_platform_fulfiller_queue_is_limited_to_explicit_kai_products(self):
        kai_product = Product(
            name="KAI 显式自营资源",
            gpu_model="H100",
            memory="80GB",
            price=Decimal("1"),
            cycle=[],
            stock=1,
            status="on",
            market_source="kai",
            # Exercise an incomplete legacy row: market ownership, not quote
            # metadata, controls the platform fulfilment boundary.
            source_price=None,
        )
        retired_product = Product(
            name="已退役外部报价资源",
            gpu_model="A100",
            memory="80GB",
            price=Decimal("1"),
            cycle=[],
            stock=1,
            status="on",
            market_source="vast",
            source_price=Decimal("1"),
        )
        self.db.add_all([kai_product, retired_product])
        self.db.flush()
        kai_order = Order(
            order_no="KAI-FULFILL-0001",
            user_id=self.buyer.id,
            product_id=kai_product.id,
            quantity=1,
            purchase_hours=1,
            cycle_days=0,
            amount=Decimal("1"),
            status="paid",
            purchase_type="usage",
        )
        retired_order = Order(
            order_no="RETIRED-FULFILL-0001",
            user_id=self.buyer.id,
            product_id=retired_product.id,
            quantity=1,
            purchase_hours=1,
            cycle_days=0,
            amount=Decimal("1"),
            status="paid",
            purchase_type="usage",
        )
        self.db.add_all([kai_order, retired_order])
        self.db.commit()

        original = settings.PLATFORM_FULFILLMENT_USER_IDS
        try:
            settings.PLATFORM_FULFILLMENT_USER_IDS = str(self.admin.id)
            queue = supplier_orders(None, self.admin, self.db)["data"]
            with self.assertRaises(BizError) as retired_delivery:
                deliver_ssh(
                    retired_order.id,
                    OrderDeliverIn(ssh_info="ssh ubuntu@192.0.2.99 -p 22"),
                    self.admin,
                    self.db,
                    "admin",
                )
            self.assertEqual(retired_delivery.exception.status_code, 403)
        finally:
            settings.PLATFORM_FULFILLMENT_USER_IDS = original

        self.assertEqual([item["order_no"] for item in queue], ["KAI-FULFILL-0001"])
        self.assertTrue(queue[0]["can_deliver"])


if __name__ == "__main__":
    unittest.main()
