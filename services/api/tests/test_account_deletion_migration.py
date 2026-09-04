"""Narrow migration tests: only synthesized in-memory/temporary SQLite files."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError

import migrate_account_deletion as migration


def synthetic_engine(url="sqlite://"):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def seed_legacy(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL, "
            "phone VARCHAR(20) NOT NULL UNIQUE, password TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (1, 'synthetic-a', '13800000001', 'synthetic-hash-a'), "
            "(2, 'synthetic-b', '13800000002', 'synthetic-hash-b')"
        )
        connection.exec_driver_sql("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount TEXT, status TEXT)")
        connection.exec_driver_sql("CREATE INDEX synthetic_order_status ON orders(status)")
        connection.exec_driver_sql("INSERT INTO orders VALUES (9, 1, '125.678900', 'completed')")
        connection.exec_driver_sql("CREATE TABLE wallet (id INTEGER PRIMARY KEY, balance TEXT)")
        connection.exec_driver_sql("INSERT INTO wallet VALUES (1, '999.123456')")
        connection.exec_driver_sql("CREATE TABLE price_history (id INTEGER PRIMARY KEY, price TEXT)")
        connection.exec_driver_sql("INSERT INTO price_history VALUES (1, '3.4567')")
        connection.exec_driver_sql("CREATE TABLE synthetic_audit (entry TEXT)")
        connection.exec_driver_sql(
            "CREATE TRIGGER synthetic_order_audit AFTER UPDATE ON orders BEGIN "
            "INSERT INTO synthetic_audit VALUES ('changed'); END"
        )


def snapshot(engine, *, other_only=False):
    """Exact schema and row fingerprint, including indexes and triggers."""
    with engine.connect() as connection:
        definitions = connection.exec_driver_sql(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).all()
        if other_only:
            definitions = [row for row in definitions if row[2] not in {"users", migration._TABLE.name}]
        tables = [row[1] for row in definitions if row[0] == "table"]
        rows = tuple((name, tuple(connection.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY rowid').all())) for name in tables)
        return tuple(definitions), rows


class AccountDeletionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = synthetic_engine()
        self.addCleanup(self.engine.dispose)
        seed_legacy(self.engine)

    def test_only_deletion_schema_changes_and_existing_credentials_are_untouched(self):
        before = snapshot(self.engine, other_only=True)
        with self.engine.connect() as connection:
            credentials = connection.exec_driver_sql("SELECT id, username, phone, password FROM users ORDER BY id").all()
        changes = migration.migrate_account_deletion(self.engine)
        self.assertEqual(changes, ["users.account_status", "users.deleted_at", "account_deletion_requests"])
        self.assertEqual(snapshot(self.engine, other_only=True), before)
        self.assertEqual(set(inspect(self.engine).get_table_names()),
                         {"users", "orders", "wallet", "price_history", "synthetic_audit", "account_deletion_requests"})
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT id, username, phone, password FROM users ORDER BY id").all(), credentials)
            self.assertEqual(connection.exec_driver_sql("SELECT account_status, deleted_at FROM users ORDER BY id").all(),
                             [("active", None), ("active", None)])
        self.assertEqual({item["name"] for item in inspect(self.engine).get_indexes(migration._TABLE.name)},
                         {index.name for index in migration._TABLE.indexes})

    def test_second_run_changes_nothing_and_preserves_existing_lifecycle(self):
        migration.migrate_account_deletion(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE users SET account_status='deleting' WHERE id=1")
            connection.exec_driver_sql("UPDATE users SET account_status='deleted', deleted_at='2026-01-02 03:04:05' WHERE id=2")
        before = snapshot(self.engine)
        self.assertEqual(migration.migrate_account_deletion(self.engine), [])
        self.assertEqual(migration.migrate_account_deletion(self.engine, check_only=True), [])
        self.assertEqual(snapshot(self.engine), before)

    def test_new_table_accepts_request_and_enforces_foreign_key_and_ticket_unique(self):
        migration.migrate_account_deletion(self.engine)
        now = datetime(2026, 1, 2)
        values = dict(user_id=1, ticket_hash="a" * 64, credential_digest="b" * 64,
                      expires_at=now + timedelta(minutes=10), receipt_expires_at=now + timedelta(days=7))
        with self.engine.begin() as connection:
            connection.execute(migration._TABLE.insert().values(**values))
            row = connection.execute(migration._TABLE.select()).mappings().one()
            self.assertEqual(row["status"], "verified")
            self.assertEqual(row["cleanup_paths"], [])
        for invalid in (values, dict(values, user_id=999, ticket_hash="c" * 64)):
            with self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(migration._TABLE.insert().values(**invalid))

    def test_check_is_read_only_on_legacy_database(self):
        before = snapshot(self.engine)
        self.assertEqual(migration.migrate_account_deletion(self.engine, check_only=True),
                         ["users.account_status", "users.deleted_at", "account_deletion_requests"])
        self.assertEqual(snapshot(self.engine), before)

    def test_no_users_refuses_without_bootstrapping_any_tables(self):
        engine = synthetic_engine()
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(migration.MigrationError, "existing_users_table_required"):
            migration.migrate_account_deletion(engine)
        self.assertEqual(inspect(engine).get_table_names(), [])

    def test_incompatible_existing_deletion_table_refuses_before_altering_users(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE account_deletion_requests (id INTEGER PRIMARY KEY)")
        before = snapshot(self.engine)
        with self.assertRaisesRegex(migration.MigrationError, "incompatible_deletion_table"):
            migration.migrate_account_deletion(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_ddl_failure_rolls_back_the_added_user_columns(self):
        before = snapshot(self.engine)
        with patch.object(migration._TABLE, "create", side_effect=RuntimeError("synthetic DDL failure")):
            with self.assertRaises(RuntimeError):
                migration.migrate_account_deletion(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_missing_declared_index_is_added_without_data_changes(self):
        migration.migrate_account_deletion(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX ix_account_deletion_requests_retry_at")
        before = snapshot(self.engine)[1]
        self.assertEqual(migration.migrate_account_deletion(self.engine), ["ix_account_deletion_requests_retry_at"])
        self.assertEqual(snapshot(self.engine)[1], before)
        self.assertEqual(migration.migrate_account_deletion(self.engine), [])

    def test_cli_requires_explicit_existing_database_and_never_logs_secret_errors(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(StringIO()) as output:
            self.assertEqual(migration.main([]), 1)
        self.assertIn("explicit_database_url_required", output.getvalue())
        with tempfile.TemporaryDirectory(prefix="wod-deletion-migration-") as directory:
            missing = Path(directory) / "must-not-be-created.db"
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + missing.as_posix()}), redirect_stderr(StringIO()):
                self.assertEqual(migration.main([]), 1)
            self.assertFalse(missing.exists())
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://synthetic:secret@example.invalid/db"}), \
                patch.object(migration, "create_engine", side_effect=RuntimeError("secret SQL parameters")), \
                redirect_stderr(StringIO()) as output:
            self.assertEqual(migration.main([]), 1)
        self.assertNotIn("secret", output.getvalue())
        self.assertIn("RuntimeError", output.getvalue())

    def test_cli_migrates_only_temporary_synthetic_file_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="wod-deletion-migration-") as directory:
            url = "sqlite:///" + (Path(directory) / "synthetic.db").as_posix()
            engine = synthetic_engine(url)
            try:
                seed_legacy(engine)
                with patch.dict(os.environ, {"DATABASE_URL": url}), redirect_stdout(StringIO()):
                    before = snapshot(engine)
                    self.assertEqual(migration.main(["--check"]), 1)
                    self.assertEqual(snapshot(engine), before)
                    self.assertEqual(migration.main([]), 0)
                    migrated = snapshot(engine)
                    self.assertEqual(migration.main([]), 0)
                    self.assertEqual(migration.main(["--check"]), 0)
                    self.assertEqual(snapshot(engine), migrated)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
