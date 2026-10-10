import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import FinanceAuditLog, Order, Product, Supplier, User
from app.routers.supplier import (
    SupplierAdminProductStatusIn,
    SupplierAdminStatusIn,
    admin_manage_supplier_product,
    admin_manage_supplier_status,
)
from app.schemas.admin_account import AdminUserActionIn
from app.services.account_administration import perform_user_action
from app.services.product_purchase import product_purchase_availability


class AdminSupplierControlTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.admin = User(
            phone="13900007201", username="商家管理员", password="!", role="admin"
        )
        self.seller = User(
            phone="13900007202",
            username="待管控商家",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.buyer = User(phone="13900007203", username="订单买家", password="!")
        self.db.add_all([self.admin, self.seller, self.buyer])
        self.db.flush()
        self.supplier = Supplier(
            user_id=self.seller.id,
            company_name="商家管控测试",
            contact="联系人",
            phone=self.seller.phone,
            status="approved",
        )
        self.db.add(self.supplier)
        self.db.flush()
        self.product = Product(
            name="商家 GPU",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("12.3450"),
            stock=2,
            market_source="wod",
            supplier_id=self.supplier.id,
            status="on",
        )
        self.db.add(self.product)
        self.db.flush()
        self.db.add(Order(
            order_no="ORDER-SUPPLIER-CONTROL-1",
            user_id=self.buyer.id,
            product_id=self.product.id,
            quantity=1,
            purchase_hours=24,
            cycle_days=0,
            amount=Decimal("296.2800"),
            status="paid",
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_suspend_stops_sales_and_reactivation_requires_product_review(self):
        result = admin_manage_supplier_status(
            self.supplier.id,
            SupplierAdminStatusIn(
                action="suspend",
                expected_status="approved",
                reason="风险复核暂停经营",
            ),
            self.admin,
            self.db,
        )["data"]
        self.db.refresh(self.supplier)
        self.db.refresh(self.seller)
        self.db.refresh(self.product)
        self.assertEqual(self.supplier.status, "suspended")
        self.assertEqual(self.seller.supplier_status, "suspended")
        self.assertEqual(self.product.status, "off")
        self.assertEqual(result["open_order_count"], 1)
        self.assertTrue(result["requires_order_follow_up"])
        self.assertFalse(product_purchase_availability(self.product, self.db)[0])

        admin_manage_supplier_status(
            self.supplier.id,
            SupplierAdminStatusIn(
                action="reactivate",
                expected_status="suspended",
                reason="风险复核完成恢复经营",
            ),
            self.admin,
            self.db,
        )
        self.db.refresh(self.product)
        self.assertEqual(self.product.status, "off")

        enabled = admin_manage_supplier_product(
            self.product.id,
            SupplierAdminProductStatusIn(
                status="on",
                expected_version=self.product.version,
                reason="商品信息复核通过",
            ),
            self.admin,
            self.db,
        )["data"]
        self.assertEqual(enabled["status"], "on")
        self.assertTrue(product_purchase_availability(self.product, self.db)[0])
        self.assertEqual(self.db.query(FinanceAuditLog).count(), 3)

    def test_inactive_supplier_owner_is_never_purchasable(self):
        self.seller.account_status = "suspended"
        self.db.commit()
        self.assertFalse(product_purchase_availability(self.product, self.db)[0])

    def test_freezing_user_also_suspends_merchant_and_delists_products(self):
        perform_user_action(
            self.db,
            actor=self.admin,
            target_user_id=self.seller.id,
            data=AdminUserActionIn(
                action="freeze",
                client_request_id="supplier-account-freeze-0001",
                reason="商家账号异常需要暂停登录与销售",
            ),
        )
        self.db.refresh(self.seller)
        self.db.refresh(self.supplier)
        self.db.refresh(self.product)
        self.assertEqual(self.seller.account_status, "suspended")
        self.assertEqual(self.seller.supplier_status, "suspended")
        self.assertEqual(self.supplier.status, "suspended")
        self.assertEqual(self.product.status, "off")


if __name__ == "__main__":
    unittest.main()
