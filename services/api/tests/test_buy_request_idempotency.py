import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models import BuyRequest, User
from app.routers import buy_request as buy_request_router
from app.utils.response import BizError
from init_db import _ensure_columns, _migrate_buy_request_idempotency


class BuyRequestIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.original_matchmaking = settings.MATCHMAKING_ENABLED
        settings.MATCHMAKING_ENABLED = True
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "buy-request-idempotency.db"
        self.engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            first = User(
                username="幂等采购方一",
                phone="13931000001",
                password="!",
                role="personal",
            )
            second = User(
                username="幂等采购方二",
                phone="13931000002",
                password="!",
                role="personal",
            )
            db.add_all([first, second])
            db.commit()
            self.first_user_id = first.id
            self.second_user_id = second.id

    def tearDown(self):
        settings.MATCHMAKING_ENABLED = self.original_matchmaking
        self.engine.dispose()
        self.tempdir.cleanup()

    @staticmethod
    def _payload(client_request_id="buy-request-test-0001", **changes):
        values = {
            "client_request_id": client_request_id,
            "request_type": "online",
            "gpu_model": "H100 80GB",
            "quantity": 2,
            "gpu_hours": 48,
            "max_unit_price": 3.1234567,
            "budget": 299.999,
            "currency": "cny",
            "region": "华东",
            "billing_mode": "ondemand",
            "requirements": {"network": "10Gbps"},
            "expires_in_hours": 24,
        }
        values.update(changes)
        return buy_request_router.BuyRequestIn(**values)

    def _create(self, user_id, payload):
        with self.Session() as db:
            user = db.get(User, user_id)
            return buy_request_router.create_request(payload, user, db)

    def test_same_key_and_payload_returns_original_request(self):
        payload = self._payload()
        first = self._create(self.first_user_id, payload)
        second = self._create(self.first_user_id, payload)

        self.assertEqual(first["data"]["id"], second["data"]["id"])
        with self.Session() as db:
            self.assertEqual(db.query(BuyRequest).count(), 1)
            stored = db.query(BuyRequest).one()
            self.assertEqual(str(stored.max_unit_price), "3.123457")
            self.assertEqual(str(stored.budget), "300.00")

    def test_same_key_with_different_payload_is_rejected(self):
        self._create(self.first_user_id, self._payload())

        with self.assertRaises(BizError) as raised:
            self._create(self.first_user_id, self._payload(quantity=3))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.msg, "重复请求参数不一致，请重新提交")
        with self.Session() as db:
            self.assertEqual(db.query(BuyRequest).count(), 1)
            self.assertEqual(db.query(BuyRequest).one().quantity, 2)

    def test_same_key_is_scoped_to_the_authenticated_user(self):
        payload = self._payload(client_request_id="shared-buy-request-0001")
        first = self._create(self.first_user_id, payload)
        second = self._create(self.second_user_id, payload)

        self.assertNotEqual(first["data"]["id"], second["data"]["id"])
        with self.Session() as db:
            rows = db.query(BuyRequest).order_by(BuyRequest.id).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row.user_id for row in rows},
                {self.first_user_id, self.second_user_id},
            )

    def test_legacy_clients_without_a_key_remain_compatible(self):
        first = self._create(self.first_user_id, self._payload(client_request_id=None))
        second = self._create(self.first_user_id, self._payload(client_request_id=None))

        self.assertNotEqual(first["data"]["id"], second["data"]["id"])
        with self.Session() as db:
            self.assertEqual(db.query(BuyRequest).count(), 2)
            self.assertTrue(all(
                row.client_request_id is None
                for row in db.query(BuyRequest).all()
            ))

    def test_integrity_conflict_rechecks_and_returns_committed_request(self):
        payload = self._payload(client_request_id="integrity-recheck-0001")
        first = self._create(self.first_user_id, payload)
        real_find = buy_request_router._find_request_by_client_id
        calls = 0

        def hide_first_lookup(db, user_id, client_request_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return real_find(db, user_id, client_request_id)

        with patch.object(
            buy_request_router,
            "_find_request_by_client_id",
            side_effect=hide_first_lookup,
        ):
            retried = self._create(self.first_user_id, payload)

        self.assertEqual(calls, 2)
        self.assertEqual(first["data"]["id"], retried["data"]["id"])
        with self.Session() as db:
            self.assertEqual(db.query(BuyRequest).count(), 1)

    def test_concurrent_sqlite_submissions_return_one_request(self):
        barrier = threading.Barrier(2)

        def submit():
            with self.Session() as db:
                user = db.get(User, self.first_user_id)
                barrier.wait(timeout=5)
                result = buy_request_router.create_request(
                    self._payload(client_request_id="concurrent-buy-request-0001"),
                    user,
                    db,
                )
                return result["data"]["id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            request_ids = list(pool.map(lambda _index: submit(), range(2)))

        self.assertEqual(request_ids[0], request_ids[1])
        with self.Session() as db:
            rows = db.query(BuyRequest).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].client_request_id, "concurrent-buy-request-0001")

    def test_client_request_id_validation(self):
        self.assertEqual(
            self._payload(client_request_id="request-0001").client_request_id,
            "request-0001",
        )
        for invalid in ("short", "request key 0001", "request/key/0001", "x" * 65):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self._payload(client_request_id=invalid)


class BuyRequestIdempotencyMigrationTests(unittest.TestCase):
    def test_legacy_table_migration_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'legacy.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE buy_requests ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "gpu_model VARCHAR(64))"
                ))
                conn.execute(text(
                    "INSERT INTO buy_requests (id, user_id, gpu_model) VALUES "
                    "(1, 7, 'A100'), (2, 7, 'A100')"
                ))

            for _run in range(2):
                _ensure_columns(engine)
                _migrate_buy_request_idempotency(engine)

            columns = {
                item["name"] for item in inspect(engine).get_columns("buy_requests")
            }
            self.assertIn("client_request_id", columns)
            scoped = [
                item for item in inspect(engine).get_indexes("buy_requests")
                if item.get("unique")
                and item.get("column_names") == ["user_id", "client_request_id"]
            ]
            self.assertEqual(len(scoped), 1)
            with engine.connect() as conn:
                legacy_rows = conn.execute(text(
                    "SELECT id, user_id, gpu_model, client_request_id "
                    "FROM buy_requests ORDER BY id"
                )).all()
            self.assertEqual(
                legacy_rows,
                [(1, 7, "A100", None), (2, 7, "A100", None)],
            )

            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO buy_requests "
                    "(id, user_id, gpu_model, client_request_id) VALUES "
                    "(3, 7, 'H100', NULL), "
                    "(4, 7, 'H100', 'shared-request-0001'), "
                    "(5, 8, 'H100', 'shared-request-0001')"
                ))
            with self.assertRaises(IntegrityError):
                with engine.begin() as conn:
                    conn.execute(text(
                        "INSERT INTO buy_requests "
                        "(id, user_id, gpu_model, client_request_id) VALUES "
                        "(6, 7, 'H100', 'shared-request-0001')"
                    ))
            engine.dispose()

    def test_half_migrated_table_with_column_gains_unique_index(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder) / 'partial.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE buy_requests ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "client_request_id VARCHAR(64))"
                ))

            _migrate_buy_request_idempotency(engine)
            scoped = [
                item for item in inspect(engine).get_indexes("buy_requests")
                if item.get("unique")
                and item.get("column_names") == ["user_id", "client_request_id"]
            ]
            self.assertEqual(len(scoped), 1)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
