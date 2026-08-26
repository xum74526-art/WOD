import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import *  # noqa: F401,F403 - register the complete metadata
from app.models.ledger import Ledger
from app.models.market_price import MarketSourceStatus
from app.models.order import Order
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from app.models.wallet import Wallet
from app.routers.order import create_order, renew_order
from app.schemas.order import OrderCreateIn, OrderRenewIn
from app.utils.response import BizError
from init_db import _ensure_columns, _migrate_order_request_scope


class OrderRenewalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Path(self.temp_dir.name) / "renewal.sqlite3"
        self.engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.factory() as db:
            user = User(username="renew-user", phone="13900001001", password="test")
            db.add(user)
            db.flush()
            db.add(Wallet(user_id=user.id, balance=Decimal("100"), frozen=Decimal("0")))
            db.add(MarketSourceStatus(
                source="kai", enabled=True, status="ok", refresh_seconds=300,
                sample_count=1, last_attempt_at=now, last_success_at=now,
            ))
            product = Product(
                name="KAI RTX4090", gpu_model="RTX4090", memory="24GB",
                price=Decimal("0.1"), cycle=[], stock=3, status="on",
                market_source="kai", external_product_id="renew-kai-4090",
                source_price=Decimal("0.1"), source_currency="CNY",
                source_max_configurable_quantity=4, platform_stock_cap=3,
                price_updated_at=now,
            )
            db.add(product)
            db.flush()
            order = Order(
                order_no="WODRENEW0001", user_id=user.id, product_id=product.id,
                quantity=1, cycle_days=0, purchase_hours=24,
                amount=Decimal("2.3952"), status="completed", purchase_type="usage",
                start_at=now - timedelta(hours=24), end_at=now - timedelta(hours=1),
            )
            db.add(order)
            db.commit()
            self.user_id = user.id
            self.product_id = product.id
            self.order_id = order.id

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_renewal_request_id_is_required_and_bounded(self):
        with self.assertRaises(ValidationError):
            OrderRenewIn(hours=1)
        with self.assertRaises(ValidationError):
            OrderRenewIn(hours=1, client_request_id="short")

    def test_duplicate_request_returns_identical_snapshot_and_charges_once(self):
        request = OrderRenewIn(hours=6, client_request_id="renew-repeat-0001")
        with self.factory() as db:
            user = SimpleNamespace(id=self.user_id)
            first = renew_order(self.order_id, request, user, db, "android")
            second = renew_order(self.order_id, request, user, db, "android")
            self.assertEqual(first, second)
            order = db.get(Order, self.order_id)
            wallet = db.query(Wallet).filter(Wallet.user_id == self.user_id).one()
            self.assertEqual(order.purchase_hours, 30)
            self.assertEqual(wallet.balance, Decimal("99.401200"))
            self.assertEqual(db.query(OrderRenewal).count(), 1)
            renewal = db.query(OrderRenewal).one()
            self.assertEqual(renewal.created_platform, "android")
            self.assertEqual(order.last_modified_platform, "android")
            self.assertEqual(first["data"]["created_platform"], "legacy")
            self.assertEqual(first["data"]["last_modified_platform"], "android")
            ledgers = db.query(Ledger).filter(Ledger.ref_order_renewal_id == renewal.id).all()
            self.assertEqual(len(ledgers), 1)
            self.assertIsNone(ledgers[0].ref_order_id)
            self.assertEqual(ledgers[0].event_key, f"order_renewal:{renewal.id}")
            with self.assertRaises(BizError):
                renew_order(
                    self.order_id,
                    OrderRenewIn(hours=7, client_request_id="renew-repeat-0001"),
                    user,
                    db,
                )

    def test_expired_completed_order_restarts_from_now_and_becomes_running(self):
        before = datetime.now(timezone.utc)
        with self.factory() as db:
            result = renew_order(
                self.order_id,
                OrderRenewIn(hours=6, client_request_id="renew-expired-0001"),
                SimpleNamespace(id=self.user_id),
                db,
            )["data"]
            order = db.get(Order, self.order_id)
            end_at = order.end_at.replace(tzinfo=timezone.utc) if order.end_at.tzinfo is None else order.end_at
            self.assertEqual(order.status, "running")
            self.assertGreaterEqual(end_at, before + timedelta(hours=6))
            self.assertLess(end_at, datetime.now(timezone.utc) + timedelta(hours=6, seconds=5))
            self.assertEqual(result["renewal_purchase_hours"], 6)
            self.assertEqual(result["renewal_new_end_at"], result["end_at"])

    def test_competing_request_ids_are_serialized_without_lost_update(self):
        def run(request_id: str):
            with self.factory() as db:
                return renew_order(
                    self.order_id,
                    OrderRenewIn(hours=1, client_request_id=request_id),
                    SimpleNamespace(id=self.user_id),
                    db,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, ("renew-race-000001", "renew-race-000002")))
        self.assertEqual(len(results), 2)
        with self.factory() as db:
            order = db.get(Order, self.order_id)
            wallet = db.query(Wallet).filter(Wallet.user_id == self.user_id).one()
            self.assertEqual(order.purchase_hours, 26)
            self.assertEqual(order.status, "running")
            self.assertEqual(wallet.balance, Decimal("99.800400"))
            self.assertEqual(db.query(OrderRenewal).count(), 2)
            self.assertEqual(
                db.query(Ledger).filter(Ledger.ref_order_renewal_id.isnot(None)).count(),
                2,
            )

    def test_legacy_wod_day_order_keeps_day_cycle_renewal_semantics(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.factory() as db:
            seller = User(username="seller", phone="13900001003", password="test", role="supplier")
            db.add(seller)
            db.flush()
            supplier = Supplier(
                user_id=seller.id, company_name="Legacy WOD", contact="Seller",
                phone="13900001003", status="approved",
            )
            db.add(supplier)
            db.flush()
            seller_wallet = Wallet(
                user_id=seller.id,
                balance=Decimal("0"),
                frozen=Decimal("0"),
                withdrawable_balance=Decimal("0"),
            )
            db.add(seller_wallet)
            product = Product(
                name="WOD Legacy", gpu_model="A800", memory="80GB",
                price=Decimal("0.1"), cycle=[1, 7, 30], stock=1,
                market_source="wod", supplier_id=supplier.id, status="on",
            )
            db.add(product)
            db.flush()
            order = Order(
                order_no="WODRENEWLEGACY", user_id=self.user_id, product_id=product.id,
                quantity=1, cycle_days=30, purchase_hours=None,
                amount=Decimal("72"), status="completed", purchase_type="usage",
                start_at=now - timedelta(days=30), end_at=now + timedelta(days=1),
            )
            db.add(order)
            db.commit()
            original_end = order.end_at

            result = renew_order(
                order.id,
                OrderRenewIn(cycle_days=1, client_request_id="renew-legacy-0001"),
                SimpleNamespace(id=self.user_id),
                db,
            )["data"]
            db.refresh(order)
            self.assertIsNone(order.purchase_hours)
            self.assertEqual(order.cycle_days, 31)
            self.assertEqual(order.end_at, original_end + timedelta(days=1))
            self.assertEqual(result["purchase_unit"], "day")
            self.assertEqual(result["renewal_cycle_days"], 1)
            self.assertIsNone(result["renewal_purchase_hours"])
            db.refresh(seller_wallet)
            self.assertEqual(seller_wallet.balance, Decimal("2.160000"))
            self.assertEqual(seller_wallet.withdrawable_balance, Decimal("2.160000"))

    def test_different_users_can_create_orders_with_the_same_request_id(self):
        with self.factory() as db:
            other = User(username="other", phone="13900001002", password="test")
            db.add(other)
            db.flush()
            db.add(Wallet(user_id=other.id, balance=Decimal("100"), frozen=Decimal("0")))
            db.commit()
            request_id = "shared-order-0001"
            payload = OrderCreateIn(
                product_id=self.product_id, quantity=1, hours=1,
                client_request_id=request_id,
            )
            first = create_order(payload, SimpleNamespace(id=self.user_id), db, "web")
            second = create_order(payload, SimpleNamespace(id=other.id), db, "ios")
            self.assertNotEqual(first["data"]["id"], second["data"]["id"])
            rows = db.query(Order).filter(Order.client_request_id == request_id).all()
            self.assertEqual({row.user_id for row in rows}, {self.user_id, other.id})
            self.assertEqual(
                {row.user_id: row.created_platform for row in rows},
                {self.user_id: "web", other.id: "ios"},
            )


class OrderRequestScopeMigrationTests(unittest.TestCase):
    def test_legacy_orders_gain_explicit_legacy_platform_attribution(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'platform.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE orders (id INTEGER PRIMARY KEY, quantity INTEGER)"
                ))
                conn.execute(text("INSERT INTO orders (id, quantity) VALUES (1, NULL)"))
            _ensure_columns(engine)
            columns = {item["name"] for item in inspect(engine).get_columns("orders")}
            self.assertIn("created_platform", columns)
            self.assertIn("last_modified_platform", columns)
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT quantity, created_platform, last_modified_platform FROM orders"
                )).one()
            self.assertEqual(tuple(row), (1, "legacy", "legacy"))
            engine.dispose()

    def test_table_level_global_unique_is_rebuilt_as_per_user_unique(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'legacy.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE orders ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "client_request_id VARCHAR(64), UNIQUE(client_request_id))"
                ))
                conn.execute(text(
                    "INSERT INTO orders (id, user_id, client_request_id) "
                    "VALUES (1, 1, 'shared-request-01')"
                ))
            _migrate_order_request_scope(engine)
            unique_shapes = {
                tuple(item.get("column_names") or [])
                for item in inspect(engine).get_indexes("orders") + inspect(engine).get_unique_constraints("orders")
                if item.get("unique")
            }
            self.assertIn(("user_id", "client_request_id"), unique_shapes)
            self.assertNotIn(("client_request_id",), unique_shapes)
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO orders (id, user_id, client_request_id) "
                    "VALUES (2, 2, 'shared-request-01')"
                ))
            with self.assertRaises(IntegrityError):
                with engine.begin() as conn:
                    conn.execute(text(
                        "INSERT INTO orders (id, user_id, client_request_id) "
                        "VALUES (3, 1, 'shared-request-01')"
                    ))
            engine.dispose()

    def test_legacy_global_unique_index_is_dropped_without_rebuilding_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'legacy-index.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE orders ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, client_request_id VARCHAR(64))"
                ))
                conn.execute(text(
                    "CREATE UNIQUE INDEX ix_orders_client_request_id "
                    "ON orders (client_request_id) WHERE client_request_id IS NOT NULL"
                ))
                conn.execute(text(
                    "INSERT INTO orders (id, user_id, client_request_id) "
                    "VALUES (1, 1, 'shared-request-02')"
                ))
            _migrate_order_request_scope(engine)
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO orders (id, user_id, client_request_id) "
                    "VALUES (2, 2, 'shared-request-02')"
                ))
                rows = conn.execute(text("SELECT id FROM orders ORDER BY id")).all()
            self.assertEqual(rows, [(1,), (2,)])
            scoped = [
                item for item in inspect(engine).get_indexes("orders")
                if item.get("unique")
                and item.get("column_names") == ["user_id", "client_request_id"]
            ]
            self.assertEqual(len(scoped), 1)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
