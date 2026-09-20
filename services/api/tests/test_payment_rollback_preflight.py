import hashlib
import io
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import preflight_payment_rollback as rollback_preflight


REPOSITORY = Path(__file__).resolve().parents[3]


class PaymentRollbackPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "rollback.sqlite3"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE withdrawal_orders (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    payout_actor_id INTEGER
                );
                CREATE TABLE payment_instruction_grants (
                    id INTEGER PRIMARY KEY,
                    withdrawal_id INTEGER NOT NULL,
                    used_at DATETIME
                );
                CREATE TABLE payment_orders (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL
                );
                CREATE TABLE payment_refunds (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL
                );
                CREATE TABLE payment_refund_requests (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL
                );
                """
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def insert(self, statement: str, parameters: tuple = ()) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(statement, parameters)
            connection.commit()

    def inspect_without_writes(self) -> tuple[rollback_preflight.RollbackBlocker, ...]:
        before = self.database_path.read_bytes()
        before_digest = hashlib.sha256(before).hexdigest()
        engine = create_engine(
            f"sqlite:///{self.database_path}",
            poolclass=NullPool,
        )
        try:
            blockers = rollback_preflight.inspect_payment_rollback_blockers(engine)
        finally:
            engine.dispose()
        after = self.database_path.read_bytes()
        self.assertEqual(hashlib.sha256(after).hexdigest(), before_digest)
        self.assertEqual(after, before)
        return blockers

    @staticmethod
    def blocker_codes(
        blockers: tuple[rollback_preflight.RollbackBlocker, ...],
    ) -> set[str]:
        return {blocker.code for blocker in blockers}

    def test_zero_or_terminal_state_passes_without_writing_database(self):
        self.insert(
            "INSERT INTO withdrawal_orders (id, status, payout_actor_id) VALUES (1, 'paid', 7)"
        )
        self.insert(
            "INSERT INTO payment_instruction_grants (id, withdrawal_id, used_at) "
            "VALUES (1, 1, NULL)"
        )
        self.insert("INSERT INTO payment_orders (id, status) VALUES (1, 'refunded')")
        self.insert("INSERT INTO payment_refunds (id, status) VALUES (1, 'succeeded')")
        self.insert(
            "INSERT INTO payment_refund_requests (id, status) VALUES (1, 'rejected')"
        )

        self.assertEqual(self.inspect_without_writes(), ())

    def test_cli_zero_state_passes_without_writing_database(self):
        before = self.database_path.read_bytes()
        stdout = io.StringIO()
        stderr = io.StringIO()
        database_url = f"sqlite:///{self.database_path}"

        with patch.dict(os.environ, {"DATABASE_URL": database_url}), patch(
            "sys.stdout", stdout
        ), patch("sys.stderr", stderr):
            self.assertEqual(rollback_preflight.main(), 0)

        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("no in-flight payment or payout state", stdout.getvalue())
        self.assertNotIn(str(self.database_path), stdout.getvalue())
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_each_active_withdrawal_status_refuses_rollback(self):
        for index, status in enumerate(
            rollback_preflight.ACTIVE_WITHDRAWAL_STATUSES,
            start=1,
        ):
            with self.subTest(status=status):
                self.insert(
                    "INSERT INTO withdrawal_orders (id, status) VALUES (?, ?)",
                    (index, status),
                )

        blockers = self.inspect_without_writes()
        self.assertEqual(
            {blocker.code: blocker.count for blocker in blockers},
            {"withdrawal_orders_in_flight": 2},
        )

    def test_unused_instruction_grant_for_active_withdrawal_refuses_rollback(self):
        self.insert(
            "INSERT INTO withdrawal_orders (id, status, payout_actor_id) "
            "VALUES (1, 'manual_payment_pending', 8)"
        )
        self.insert(
            "INSERT INTO payment_instruction_grants (id, withdrawal_id, used_at) "
            "VALUES (1, 1, NULL)"
        )
        self.insert(
            "INSERT INTO payment_instruction_grants (id, withdrawal_id, used_at) "
            "VALUES (2, 1, '2026-09-18 00:00:00')"
        )

        blockers = self.inspect_without_writes()

        self.assertEqual(
            {blocker.code: blocker.count for blocker in blockers},
            {
                "withdrawal_orders_in_flight": 1,
                "payment_instruction_grants_unused": 1,
            },
        )

    def test_every_active_payment_order_status_refuses_rollback(self):
        for index, status in enumerate(
            rollback_preflight.ACTIVE_PAYMENT_ORDER_STATUSES,
            start=1,
        ):
            self.insert(
                "INSERT INTO payment_orders (id, status) VALUES (?, ?)",
                (index, status),
            )

        blockers = self.inspect_without_writes()

        self.assertEqual(
            {blocker.code: blocker.count for blocker in blockers},
            {
                "payment_orders_in_flight": len(
                    rollback_preflight.ACTIVE_PAYMENT_ORDER_STATUSES
                )
            },
        )

    def test_every_actual_nonterminal_refund_status_refuses_rollback(self):
        self.assertEqual(
            rollback_preflight.ACTIVE_PAYMENT_REFUND_STATUSES,
            ("preparing", "submitting", "unknown"),
        )
        for index, status in enumerate(
            rollback_preflight.ACTIVE_PAYMENT_REFUND_STATUSES,
            start=1,
        ):
            self.insert(
                "INSERT INTO payment_refunds (id, status) VALUES (?, ?)",
                (index, status),
            )

        blockers = self.inspect_without_writes()

        self.assertEqual(
            {blocker.code: blocker.count for blocker in blockers},
            {"payment_refunds_in_flight": 3},
        )

    def test_pending_customer_refund_requests_refuse_rollback(self):
        for index, status in enumerate(
            rollback_preflight.ACTIVE_PAYMENT_REFUND_REQUEST_STATUSES,
            start=1,
        ):
            self.insert(
                "INSERT INTO payment_refund_requests (id, status) VALUES (?, ?)",
                (index, status),
            )

        blockers = self.inspect_without_writes()

        self.assertEqual(
            {blocker.code: blocker.count for blocker in blockers},
            {"payment_refund_requests_in_flight": 3},
        )

    def test_missing_safety_schema_fails_closed_without_writing_database(self):
        self.insert("DROP TABLE payment_refunds")
        before = self.database_path.read_bytes()
        engine = create_engine(
            f"sqlite:///{self.database_path}",
            poolclass=NullPool,
        )
        try:
            with self.assertRaisesRegex(
                rollback_preflight.PaymentRollbackPreflightError,
                "required_schema_missing",
            ):
                rollback_preflight.inspect_payment_rollback_blockers(engine)
        finally:
            engine.dispose()
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_cli_does_not_echo_database_url_or_driver_errors(self):
        secret_url = "postgresql://private-user:private-password@127.0.0.1:1/private-db"
        stderr = io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": secret_url}), patch.object(
            rollback_preflight,
            "create_engine",
            side_effect=RuntimeError(f"failed to connect to {secret_url}"),
        ), patch("sys.stderr", stderr):
            self.assertEqual(rollback_preflight.main(), 1)

        output = stderr.getvalue()
        self.assertIn("database_check_failed", output)
        self.assertNotIn("private-user", output)
        self.assertNotIn("private-password", output)
        self.assertNotIn("private-db", output)

    def test_rollback_preflight_is_never_in_a_normal_service_entrypoint(self):
        entrypoints = (
            REPOSITORY / "infra" / "kai-api.service",
            REPOSITORY / "services" / "api" / "docker-entrypoint.sh",
            REPOSITORY / "services" / "api" / "Dockerfile",
        )
        for path in entrypoints:
            with self.subTest(path=path.name):
                self.assertNotIn(
                    "preflight_payment_rollback.py",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
