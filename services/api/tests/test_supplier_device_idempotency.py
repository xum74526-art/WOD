import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import Product, Supplier, User
from app.routers import supplier as supplier_router
from app.schemas.supplier import SupplierDeviceCreateIn
from init_db import _migrate_product_create_idempotency


class SupplierDeviceConcurrentIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tempdir.name, "supplier-idempotency.sqlite")
        self.engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            user = User(
                username="并发上架商家",
                phone="13900000991",
                password="!",
                role="supplier",
                supplier_status="approved",
            )
            db.add(user)
            db.flush()
            supplier = Supplier(
                user_id=user.id,
                company_name="并发上架测试商家",
                contact="测试联系人",
                phone=user.phone,
                status="approved",
            )
            db.add(supplier)
            db.commit()
            self.user_id = int(user.id)
            self.supplier_id = int(supplier.id)

    def tearDown(self):
        self.engine.dispose()
        self.tempdir.cleanup()

    @staticmethod
    def _payload():
        return {
            "client_request_id": "supplier-device-concurrent-0001",
            "name": "H100 80GB 并发资源",
            "gpu_model": "H100",
            "memory": "80GB",
            "price": "24.8000",
            "stock": 4,
            "desc": "并发幂等验证",
            "region_code": "east_china",
            "region_name": "华东",
            "city": "上海",
        }

    def test_concurrent_same_intent_creates_one_product(self):
        barrier = threading.Barrier(2)
        original_get_supplier = supplier_router._get_supplier

        def synchronized_get_supplier(user, db):
            supplier = original_get_supplier(user, db)
            barrier.wait(timeout=10)
            return supplier

        def create_once():
            with self.sessions() as db:
                return supplier_router.add_device(
                    SupplierDeviceCreateIn.model_validate(self._payload()),
                    SimpleNamespace(id=self.user_id),
                    db,
                )

        with patch.object(
            supplier_router,
            "_get_supplier",
            side_effect=synchronized_get_supplier,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(create_once) for _ in range(2)]
                results = [future.result(timeout=20) for future in futures]

        ids = [result["data"]["id"] for result in results]
        self.assertEqual(ids[0], ids[1])
        with self.sessions() as db:
            products = db.query(Product).filter(
                Product.supplier_id == self.supplier_id,
            ).all()
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].client_request_id, self._payload()["client_request_id"])
            self.assertEqual(len(products[0].create_request_hash or ""), 64)


class SupplierDeviceIdempotencyMigrationTests(unittest.TestCase):
    def _legacy_engine(self, *, include_request_columns: bool = False):
        database = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        database.close()
        self.addCleanup(lambda: Path(database.name).unlink(missing_ok=True))
        target = create_engine(f"sqlite:///{Path(database.name).as_posix()}")
        self.addCleanup(target.dispose)
        extra = (
            ", client_request_id VARCHAR(64), create_request_hash VARCHAR(64)"
            if include_request_columns
            else ""
        )
        with target.begin() as conn:
            conn.execute(text(
                "CREATE TABLE products ("
                "id INTEGER PRIMARY KEY, supplier_id INTEGER"
                f"{extra})"
            ))
        return target

    def test_migration_is_repeatable_and_scopes_request_id_to_supplier(self):
        target = self._legacy_engine()

        _migrate_product_create_idempotency(target)
        _migrate_product_create_idempotency(target)

        columns = {item["name"] for item in inspect(target).get_columns("products")}
        self.assertTrue({"client_request_id", "create_request_hash"}.issubset(columns))
        index = next(
            item
            for item in inspect(target).get_indexes("products")
            if item["name"] == "uq_products_supplier_client_request"
        )
        self.assertTrue(index["unique"])
        self.assertEqual(index["column_names"], ["supplier_id", "client_request_id"])

        with target.begin() as conn:
            conn.execute(text(
                "INSERT INTO products (id, supplier_id, client_request_id) "
                "VALUES (1, 1, NULL), (2, 1, NULL), "
                "(3, 1, 'supplier-device-shared'), "
                "(4, 2, 'supplier-device-shared')"
            ))
        with self.assertRaises(IntegrityError):
            with target.begin() as conn:
                conn.execute(text(
                    "INSERT INTO products (id, supplier_id, client_request_id) "
                    "VALUES (5, 1, 'supplier-device-shared')"
                ))

    def test_migration_refuses_existing_scoped_duplicates(self):
        target = self._legacy_engine(include_request_columns=True)
        with target.begin() as conn:
            conn.execute(text(
                "INSERT INTO products (id, supplier_id, client_request_id) "
                "VALUES (1, 9, 'supplier-device-duplicate'), "
                "(2, 9, 'supplier-device-duplicate')"
            ))

        with self.assertRaisesRegex(RuntimeError, "duplicate per-supplier"):
            _migrate_product_create_idempotency(target)


if __name__ == "__main__":
    unittest.main()
