import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import Product, Supplier, User
from app.routers import supplier as supplier_router
from app.utils.response import BizError, error


class SupplierDeviceCrudTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

        self.owner = self._add_supplier_user(1, "approved")
        self.other_supplier = self._add_supplier_user(2, "approved")
        self.pending_supplier = self._add_supplier_user(3, "pending")
        self.rejected_supplier = self._add_supplier_user(4, "rejected")
        self.db.commit()
        self.current_user = self.owner

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_error_handler(request: Request, exc: BizError):
            del request
            return JSONResponse(
                status_code=exc.status_code,
                content=error(exc.msg, exc.code),
            )

        def db_override():
            yield self.db

        app.include_router(supplier_router.router)
        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def _add_supplier_user(self, suffix: int, status: str) -> User:
        user = User(
            username=f"商家测试{suffix}",
            phone=f"139000001{suffix:02d}",
            password="!",
            role="supplier" if status == "approved" else "personal",
            supplier_status=status,
        )
        self.db.add(user)
        self.db.flush()
        self.db.add(Supplier(
            user_id=user.id,
            company_name=f"测试商家{suffix}",
            contact=f"联系人{suffix}",
            phone=user.phone,
            status=status,
        ))
        self.db.flush()
        return user

    @staticmethod
    def _device_payload(**overrides):
        payload = {
            "name": "RTX 5090 32GB",
            "gpu_model": "RTX 5090",
            "memory": "32GB",
            "cuda": "12.8",
            "price": "12.3456",
            "stock": 8,
            "desc": "商家自有算力资源",
            "region_code": "east_china",
            "region_name": "华东",
            "city": "上海",
        }
        payload.update(overrides)
        return payload

    def _create_owned_device(self) -> Product:
        self.current_user = self.owner
        response = self.client.post(
            "/api/supplier/devices",
            json=self._device_payload(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        product_id = response.json()["data"]["id"]
        return self.db.query(Product).filter(Product.id == product_id).one()

    def test_approved_supplier_creates_resource_without_price_conversion(self):
        product = self._create_owned_device()
        owner_record = self.db.query(Supplier).filter(
            Supplier.user_id == self.owner.id,
        ).one()

        self.assertEqual(product.supplier_id, owner_record.id)
        self.assertEqual(product.price, Decimal("12.3456"))
        self.assertEqual(product.stock, 8)
        self.assertEqual(product.status, "on")
        self.assertEqual(product.market_source, "wod")
        self.assertEqual(product.stock_semantics, "supplier_reported_inventory")
        self.assertEqual(product.cycle, [])
        self.assertEqual(product.region_code, "east_china")
        self.assertEqual(product.version, 1)

        response = self.client.get("/api/supplier/devices", params={"status_filter": "all"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"][0]["version"], 1)

    def test_same_create_intent_reuses_resource_after_later_product_edits(self):
        request_id = "supplier-device-retry-0001"
        initial_payload = self._device_payload(
            client_request_id=request_id,
            price="12.3000",
        )
        first = self.client.post("/api/supplier/devices", json=initial_payload)
        self.assertEqual(first.status_code, 200, first.text)
        product_id = first.json()["data"]["id"]

        product = self.db.query(Product).filter(Product.id == product_id).one()
        product.price = Decimal("14.0000")
        product.stock = 3
        self.db.commit()
        self.db.refresh(product)

        retry = self.client.post(
            "/api/supplier/devices",
            json={**initial_payload, "price": "12.3"},
        )

        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["data"]["id"], product_id)
        self.assertEqual(retry.json()["data"]["version"], product.version)
        self.assertEqual(
            self.db.query(Product).filter(Product.supplier_id == product.supplier_id).count(),
            1,
        )

    def test_same_create_intent_rejects_different_resource_payload(self):
        request_id = "supplier-device-conflict-0001"
        first = self.client.post(
            "/api/supplier/devices",
            json=self._device_payload(client_request_id=request_id),
        )
        self.assertEqual(first.status_code, 200, first.text)

        conflict = self.client.post(
            "/api/supplier/devices",
            json=self._device_payload(
                client_request_id=request_id,
                name="RTX 5090 第二台资源",
            ),
        )

        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertIn("参数不一致", conflict.json()["msg"])
        self.assertEqual(self.db.query(Product).count(), 1)

    def test_unique_conflict_recovers_when_initial_idempotency_lookup_misses(self):
        request_id = "supplier-device-race-recovery-0001"
        payload = self._device_payload(client_request_id=request_id)
        first = self.client.post("/api/supplier/devices", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        original_find = supplier_router._find_device_by_client_request
        lookup_count = 0

        def miss_then_find(db, supplier_id, client_request_id):
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                return None
            return original_find(db, supplier_id, client_request_id)

        with patch.object(
            supplier_router,
            "_find_device_by_client_request",
            side_effect=miss_then_find,
        ):
            retry = self.client.post("/api/supplier/devices", json=payload)

        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["data"]["id"], first.json()["data"]["id"])
        self.assertEqual(lookup_count, 2)
        self.assertEqual(self.db.query(Product).count(), 1)

    def test_create_intent_is_scoped_to_supplier(self):
        request_id = "supplier-device-shared-0001"
        first = self.client.post(
            "/api/supplier/devices",
            json=self._device_payload(client_request_id=request_id),
        )
        self.assertEqual(first.status_code, 200, first.text)

        self.current_user = self.other_supplier
        second = self.client.post(
            "/api/supplier/devices",
            json=self._device_payload(client_request_id=request_id),
        )

        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(self.db.query(Product).count(), 2)

    def test_legacy_create_without_request_id_remains_compatible(self):
        first = self.client.post("/api/supplier/devices", json=self._device_payload())
        second = self.client.post("/api/supplier/devices", json=self._device_payload())

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(self.db.query(Product).count(), 2)

    def test_supplier_cannot_update_another_suppliers_resource(self):
        product = self._create_owned_device()
        self.current_user = self.other_supplier

        response = self.client.put(
            f"/api/supplier/devices/{product.id}",
            json={"name": "越权修改", "price": "1.0000", "stock": 1},
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.db.refresh(product)
        self.assertEqual(product.name, "RTX 5090 32GB")
        self.assertEqual(product.price, Decimal("12.3456"))
        self.assertEqual(product.stock, 8)

    def test_pending_and_rejected_suppliers_cannot_write_resources(self):
        product = self._create_owned_device()

        for user in (self.pending_supplier, self.rejected_supplier):
            with self.subTest(status=user.supplier_status, operation="create"):
                self.current_user = user
                response = self.client.post(
                    "/api/supplier/devices",
                    json=self._device_payload(name=f"未审核资源{user.id}"),
                )
                self.assertEqual(response.status_code, 403, response.text)

            with self.subTest(status=user.supplier_status, operation="update"):
                response = self.client.put(
                    f"/api/supplier/devices/{product.id}",
                    json={"stock": 0},
                )
                self.assertEqual(response.status_code, 403, response.text)

        self.db.refresh(product)
        self.assertEqual(product.stock, 8)

    def test_create_and_update_reject_out_of_range_price_and_stock(self):
        self.current_user = self.owner
        invalid_create_values = (
            {"price": "0"},
            {"price": "0.00001"},
            {"price": "100000.0001"},
            {"stock": -1},
            {"stock": 100001},
        )
        for overrides in invalid_create_values:
            with self.subTest(operation="create", overrides=overrides):
                response = self.client.post(
                    "/api/supplier/devices",
                    json=self._device_payload(**overrides),
                )
                self.assertEqual(response.status_code, 422, response.text)

        product = self._create_owned_device()
        invalid_updates = (
            {"price": "0"},
            {"price": "0.00001"},
            {"price": "100000.0001"},
            {"stock": -1},
            {"stock": 100001},
        )
        for payload in invalid_updates:
            with self.subTest(operation="update", payload=payload):
                response = self.client.put(
                    f"/api/supplier/devices/{product.id}",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422, response.text)

        self.db.refresh(product)
        self.assertEqual(product.price, Decimal("12.3456"))
        self.assertEqual(product.stock, 8)

    def test_supplier_can_delist_and_relist_owned_resource(self):
        product = self._create_owned_device()

        for expected_status in ("off", "on"):
            with self.subTest(status=expected_status):
                previous_version = product.version
                response = self.client.put(
                    f"/api/supplier/devices/{product.id}",
                    json={"status": expected_status, "expected_version": previous_version},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["data"]["updated"])
                self.db.refresh(product)
                self.assertEqual(product.status, expected_status)
                self.assertEqual(product.version, previous_version + 1)
                self.assertEqual(response.json()["data"]["version"], product.version)

    def test_stale_supplier_edit_cannot_restore_reserved_inventory(self):
        product = self._create_owned_device()
        edit_version = product.version

        # Simulate an order reserving one unit after the merchant opened the
        # edit form. Product's mapper increments the row version automatically.
        product.stock = 7
        self.db.commit()
        self.db.refresh(product)
        self.assertEqual(product.version, edit_version + 1)

        response = self.client.put(
            f"/api/supplier/devices/{product.id}",
            json={
                "name": "旧页面名称",
                "stock": 8,
                "expected_version": edit_version,
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("刷新后重新编辑", response.json()["msg"])
        self.db.refresh(product)
        self.assertEqual(product.name, "RTX 5090 32GB")
        self.assertEqual(product.stock, 7)
        self.assertEqual(product.version, edit_version + 1)

    def test_legacy_supplier_update_without_version_remains_compatible(self):
        product = self._create_owned_device()

        response = self.client.put(
            f"/api/supplier/devices/{product.id}",
            json={"stock": 9},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(product)
        self.assertEqual(product.stock, 9)
        self.assertEqual(product.version, 2)


if __name__ == "__main__":
    unittest.main()
