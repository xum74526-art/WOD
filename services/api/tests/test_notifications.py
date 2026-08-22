import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Notification, Order, Product, Supplier, User  # noqa: F401
from app.routers import notification as notification_router
from app.schemas.notification import NotificationPreferenceUpdate
from app.services.notification_service import (
    _sync_order_notifications,
    create_notification,
    get_or_create_preferences,
)
from app.utils.response import BizError
from init_db import _ensure_columns


class NotificationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user_a = User(phone="13900000101", username="通知用户 A", password="!")
        self.user_b = User(phone="13900000102", username="通知用户 B", password="!")
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

    def tearDown(self):
        self.db.close()

    def test_preferences_are_persisted_per_account(self):
        result = notification_router.get_preferences(self.user_a, self.db)["data"]
        self.assertTrue(result["preferences"]["order_enabled"])
        self.assertTrue(result["delivery"]["in_app_enabled"])
        self.assertFalse(result["delivery"]["system_push_configured"])

        updated = notification_router.update_preferences(
            NotificationPreferenceUpdate(order_enabled=False, device_enabled=False),
            self.user_a,
            self.db,
        )["data"]["preferences"]
        self.assertFalse(updated["order_enabled"])
        self.assertFalse(updated["device_enabled"])
        other = get_or_create_preferences(self.db, self.user_b.id)
        self.assertTrue(other.order_enabled)
        self.assertTrue(other.device_enabled)

    def test_disabled_category_suppresses_new_event(self):
        preferences = get_or_create_preferences(self.db, self.user_a.id)
        preferences.order_enabled = False
        self.db.commit()
        result = create_notification(
            self.db,
            user_id=self.user_a.id,
            title="不应创建",
            notification_type="order",
            dedupe_key="order:blocked",
        )
        self.db.commit()
        self.assertIsNone(result)
        self.assertEqual(
            self.db.query(Notification).filter(Notification.user_id == self.user_a.id).count(),
            0,
        )

    def test_list_is_paginated_and_account_scoped(self):
        for index in range(25):
            create_notification(
                self.db,
                user_id=self.user_a.id,
                title=f"消息 {index}",
                notification_type="system",
                dedupe_key=f"test:a:{index}",
                respect_preferences=False,
            )
        create_notification(
            self.db,
            user_id=self.user_b.id,
            title="B 的私有消息",
            notification_type="system",
            dedupe_key="test:b:private",
            respect_preferences=False,
        )
        self.db.commit()

        first = notification_router.list_notifications(
            type_filter=None,
            unread_only=False,
            page=1,
            page_size=10,
            user=self.user_a,
            db=self.db,
        )["data"]
        second = notification_router.list_notifications(
            type_filter=None,
            unread_only=False,
            page=2,
            page_size=10,
            user=self.user_a,
            db=self.db,
        )["data"]
        # 25 business-test rows plus the factual one-time inbox status row.
        self.assertEqual(first["total"], 26)
        self.assertEqual(len(first["items"]), 10)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(second["items"]), 10)
        self.assertNotIn("B 的私有消息", {row["title"] for row in first["items"] + second["items"]})

    def test_read_operations_cannot_cross_accounts(self):
        private = create_notification(
            self.db,
            user_id=self.user_b.id,
            title="B 的私有消息",
            notification_type="system",
            respect_preferences=False,
        )
        self.db.commit()
        with self.assertRaises(BizError) as raised:
            notification_router.mark_read(private.id, self.user_a, self.db)
        self.assertEqual(raised.exception.status_code, 404)
        self.db.refresh(private)
        self.assertFalse(private.is_read)

        notification_router.mark_read(private.id, self.user_b, self.db)
        self.db.refresh(private)
        self.assertTrue(private.is_read)

    def test_mark_all_only_changes_current_account(self):
        for user in (self.user_a, self.user_b):
            create_notification(
                self.db,
                user_id=user.id,
                title=f"{user.username} 的消息",
                notification_type="system",
                respect_preferences=False,
            )
        self.db.commit()
        result = notification_router.mark_all_read(self.user_a, self.db)["data"]
        self.assertEqual(result["changed"], 1)
        own = self.db.query(Notification).filter(Notification.user_id == self.user_a.id).one()
        other = self.db.query(Notification).filter(Notification.user_id == self.user_b.id).one()
        self.assertTrue(own.is_read)
        self.assertFalse(other.is_read)

    def test_order_event_sync_notifies_buyer_and_supplier_once(self):
        supplier = Supplier(
            user_id=self.user_b.id,
            company_name="通知测试商家",
            contact="测试联系人",
            phone="13900000102",
            status="approved",
        )
        self.db.add(supplier)
        self.db.flush()
        product = Product(
            name="通知测试资源",
            gpu_model="RTX4090",
            memory="24GB",
            price=Decimal("1"),
            stock=1,
            supplier_id=supplier.id,
            status="on",
        )
        self.db.add(product)
        self.db.flush()
        order = Order(
            order_no="WOD-NOTIFY-0001",
            user_id=self.user_a.id,
            product_id=product.id,
            amount=Decimal("24"),
            cycle_days=1,
            status="paid",
            end_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        self.db.add(order)
        self.db.commit()

        _sync_order_notifications(self.db)
        self.db.commit()
        buyer_rows = self.db.query(Notification).filter(Notification.user_id == self.user_a.id).all()
        supplier_rows = self.db.query(Notification).filter(Notification.user_id == self.user_b.id).all()
        self.assertEqual(len(buyer_rows), 1)
        self.assertEqual(len(supplier_rows), 1)
        self.assertEqual(buyer_rows[0].action_url, f"/pages/order/detail?id={order.id}")
        self.assertEqual(supplier_rows[0].action_url, "/pages/supplier/orders")

        _sync_order_notifications(self.db)
        self.db.commit()
        self.assertEqual(self.db.query(Notification).count(), 2)

    def test_legacy_notification_table_receives_required_columns_idempotently(self):
        legacy_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with legacy_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE notifications ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "title VARCHAR(128) NOT NULL, content TEXT, type VARCHAR(32), "
                "is_read BOOLEAN, created_at DATETIME)"
            ))
        _ensure_columns(legacy_engine)
        _ensure_columns(legacy_engine)
        columns = {column["name"] for column in inspect(legacy_engine).get_columns("notifications")}
        self.assertTrue({"title_en", "content_en", "action_url", "dedupe_key"}.issubset(columns))


if __name__ == "__main__":
    unittest.main()
