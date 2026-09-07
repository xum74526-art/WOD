"""Narrow recovery migration tests using only synthetic SQLite databases."""

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

import migrate_account_recovery as migration


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
        connection.exec_driver_sql(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount TEXT, status TEXT)"
        )
        connection.exec_driver_sql("CREATE INDEX synthetic_order_status ON orders(status)")
        connection.exec_driver_sql("INSERT INTO orders VALUES (9, 1, '125.678900', 'completed')")
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
            definitions = [
                row
                for row in definitions
                if row[2]
                not in {"users", migration._TABLE.name, migration._MAIL_TABLE.name}
            ]
        tables = [row[1] for row in definitions if row[0] == "table"]
        rows = tuple(
            (
                name,
                tuple(connection.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY rowid').all()),
            )
            for name in tables
        )
        return tuple(definitions), rows


class AccountRecoveryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = synthetic_engine()
        self.addCleanup(self.engine.dispose)
        seed_legacy(self.engine)

    def test_only_recovery_schema_changes_and_existing_credentials_are_untouched(self):
        before = snapshot(self.engine, other_only=True)
        with self.engine.connect() as connection:
            credentials = connection.exec_driver_sql(
                "SELECT id, username, phone, password FROM users ORDER BY id"
            ).all()
        changes = migration.migrate_account_recovery(self.engine)
        self.assertEqual(
            changes,
            [
                "users.recovery_email",
                "users.recovery_email_fingerprint",
                "users.recovery_email_verified_at",
                "users.auth_version",
                migration._EMAIL_INDEX.name,
                migration._TABLE.name,
                migration._MAIL_TABLE.name,
            ],
        )
        self.assertEqual(snapshot(self.engine, other_only=True), before)
        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            {
                "users",
                "orders",
                "synthetic_audit",
                migration._TABLE.name,
                migration._MAIL_TABLE.name,
            },
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql(
                    "SELECT id, username, phone, password FROM users ORDER BY id"
                ).all(),
                credentials,
            )
            self.assertEqual(
                connection.exec_driver_sql(
                    "SELECT recovery_email, recovery_email_fingerprint, "
                    "recovery_email_verified_at, auth_version FROM users ORDER BY id"
                ).all(),
                [(None, None, None, 0), (None, None, None, 0)],
            )
        user_indexes = {
            item["name"]: item for item in inspect(self.engine).get_indexes("users")
        }
        self.assertTrue(user_indexes[migration._EMAIL_INDEX.name]["unique"])
        self.assertEqual(
            {item["name"] for item in inspect(self.engine).get_indexes(migration._TABLE.name)},
            {index.name for index in migration._TABLE.indexes},
        )
        self.assertEqual(
            {
                item["name"]
                for item in inspect(self.engine).get_indexes(
                    migration._MAIL_TABLE.name
                )
            },
            {index.name for index in migration._MAIL_TABLE.indexes},
        )

    def test_second_run_is_idempotent_and_preserves_recovery_state(self):
        migration.migrate_account_recovery(self.engine)
        now = datetime(2026, 1, 2, 3, 4, 5)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email='owner@example.test', "
                "recovery_email_fingerprint='aabb', recovery_email_verified_at=?, "
                "auth_version=7 WHERE id=1",
                (now,),
            )
            connection.execute(
                migration._TABLE.insert().values(
                    user_id=1,
                    purpose="password_reset_email",
                    token_hash="a" * 64,
                    auth_version_snapshot=7,
                    expires_at=now + timedelta(minutes=15),
                )
            )
        before = snapshot(self.engine)
        self.assertEqual(migration.migrate_account_recovery(self.engine), [])
        self.assertEqual(migration.migrate_account_recovery(self.engine, check_only=True), [])
        self.assertEqual(snapshot(self.engine), before)

    def test_token_table_enforces_foreign_key_and_hash_uniqueness(self):
        migration.migrate_account_recovery(self.engine)
        now = datetime(2026, 1, 2)
        values = dict(
            user_id=1,
            purpose="password_reset_email",
            token_hash="a" * 64,
            expires_at=now + timedelta(minutes=15),
        )
        with self.engine.begin() as connection:
            connection.execute(migration._TABLE.insert().values(**values))
            row = connection.execute(migration._TABLE.select()).mappings().one()
            self.assertEqual(row["auth_version_snapshot"], 0)
            self.assertIsNotNone(row["created_at"])
        for invalid in (
            values,
            dict(values, user_id=999, token_hash="b" * 64),
        ):
            with self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(migration._TABLE.insert().values(**invalid))

    def test_non_null_recovery_email_fingerprint_is_unique(self):
        migration.migrate_account_recovery(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email_fingerprint='same' WHERE id=1"
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email_fingerprint='same' WHERE id=2"
            )
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email_fingerprint=NULL WHERE id=1"
            )
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email_fingerprint=NULL WHERE id=2"
            )

    def test_check_is_read_only_on_legacy_database(self):
        before = snapshot(self.engine)
        self.assertEqual(
            migration.migrate_account_recovery(self.engine, check_only=True),
            [
                "users.recovery_email",
                "users.recovery_email_fingerprint",
                "users.recovery_email_verified_at",
                "users.auth_version",
                migration._EMAIL_INDEX.name,
                migration._TABLE.name,
                migration._MAIL_TABLE.name,
            ],
        )
        self.assertEqual(snapshot(self.engine), before)

    def test_no_users_refuses_without_bootstrapping_any_tables(self):
        engine = synthetic_engine()
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(migration.MigrationError, "existing_users_table_required"):
            migration.migrate_account_recovery(engine)
        self.assertEqual(inspect(engine).get_table_names(), [])

    def test_incompatible_token_table_refuses_before_altering_users(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE account_recovery_tokens (id INTEGER PRIMARY KEY)"
            )
        before = snapshot(self.engine)
        with self.assertRaisesRegex(migration.MigrationError, "incompatible_recovery_token_table"):
            migration.migrate_account_recovery(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_incompatible_mail_outbox_refuses_before_altering_users(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE account_recovery_mail_outbox (id INTEGER PRIMARY KEY)"
            )
        before = snapshot(self.engine)
        with self.assertRaisesRegex(
            migration.MigrationError,
            "incompatible_recovery_mail_outbox_table",
        ):
            migration.migrate_account_recovery(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_wrong_named_mail_token_index_is_not_accepted_as_ready(self):
        migration.migrate_account_recovery(self.engine)
        index_name = "ux_account_recovery_mail_outbox_recovery_token_id"
        with self.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX {index_name}")
            connection.exec_driver_sql(
                f"CREATE INDEX {index_name} "
                "ON account_recovery_mail_outbox(status)"
            )
        before = snapshot(self.engine)
        with self.assertRaisesRegex(
            migration.MigrationError,
            "incompatible_recovery_mail_token_index",
        ):
            migration.migrate_account_recovery(self.engine, check_only=True)
        self.assertEqual(snapshot(self.engine), before)

    def test_duplicate_legacy_fingerprint_refuses_without_mutation(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN recovery_email_fingerprint VARCHAR(64)"
            )
            connection.exec_driver_sql(
                "UPDATE users SET recovery_email_fingerprint='duplicate'"
            )
        before = snapshot(self.engine)
        with self.assertRaisesRegex(migration.MigrationError, "duplicate_recovery_email_fingerprint"):
            migration.migrate_account_recovery(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_ddl_failure_rolls_back_all_added_recovery_schema(self):
        before = snapshot(self.engine)
        with patch.object(migration._TABLE, "create", side_effect=RuntimeError("synthetic DDL failure")):
            with self.assertRaises(RuntimeError):
                migration.migrate_account_recovery(self.engine)
        self.assertEqual(snapshot(self.engine), before)

    def test_missing_declared_indexes_are_repaired_without_data_changes(self):
        migration.migrate_account_recovery(self.engine)
        token_index = "ix_account_recovery_tokens_expires_at"
        with self.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX {token_index}")
        before_rows = snapshot(self.engine)[1]
        self.assertEqual(migration.migrate_account_recovery(self.engine), [token_index])
        self.assertEqual(snapshot(self.engine)[1], before_rows)
        mail_index = "ix_account_recovery_mail_outbox_expires_at"
        with self.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX {mail_index}")
        before_rows = snapshot(self.engine)[1]
        self.assertEqual(migration.migrate_account_recovery(self.engine), [mail_index])
        self.assertEqual(snapshot(self.engine)[1], before_rows)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX {migration._EMAIL_INDEX.name}")
        before_rows = snapshot(self.engine)[1]
        self.assertEqual(
            migration.migrate_account_recovery(self.engine),
            [migration._EMAIL_INDEX.name],
        )
        self.assertEqual(snapshot(self.engine)[1], before_rows)
        self.assertEqual(migration.migrate_account_recovery(self.engine), [])

    def test_cli_requires_explicit_existing_database_and_never_logs_secret_errors(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(StringIO()) as output:
            self.assertEqual(migration.main([]), 1)
        self.assertIn("explicit_database_url_required", output.getvalue())
        with tempfile.TemporaryDirectory(prefix="wod-recovery-migration-") as directory:
            missing = Path(directory) / "must-not-be-created.db"
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + missing.as_posix()}), redirect_stderr(StringIO()):
                self.assertEqual(migration.main([]), 1)
            self.assertFalse(missing.exists())
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://synthetic:secret@example.invalid/db"},
        ), patch.object(
            migration,
            "create_engine",
            side_effect=RuntimeError("secret SQL parameters"),
        ), redirect_stderr(StringIO()) as output:
            self.assertEqual(migration.main([]), 1)
        self.assertNotIn("secret", output.getvalue())
        self.assertIn("RuntimeError", output.getvalue())

    def test_cli_migrates_only_temporary_file_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="wod-recovery-migration-") as directory:
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
