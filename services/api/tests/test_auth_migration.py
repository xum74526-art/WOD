import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from init_db import (
    _ensure_auth_identity_constraints,
    _ensure_columns,
    _normalize_kai_identity_issuers,
)
from app.core.config import settings


class AuthMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    def test_legacy_oauth_tables_gain_binding_and_attribution_columns(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE external_auth_flows ("
                "id INTEGER PRIMARY KEY, state_hash TEXT, code_verifier TEXT, nonce TEXT, "
                "intent TEXT, return_url TEXT, expires_at DATETIME, consumed_at DATETIME)"
            ))
            conn.execute(text(
                "CREATE TABLE external_auth_tickets ("
                "id INTEGER PRIMARY KEY, ticket_hash TEXT, user_id INTEGER, "
                "expires_at DATETIME, consumed_at DATETIME)"
            ))
        _ensure_columns(self.engine)
        inspector = inspect(self.engine)
        flow_columns = {column["name"] for column in inspector.get_columns("external_auth_flows")}
        ticket_columns = {column["name"] for column in inspector.get_columns("external_auth_tickets")}
        self.assertTrue({"user_id", "platform", "client_id", "terms_accepted"}.issubset(flow_columns))
        self.assertTrue({"platform", "client_id"}.issubset(ticket_columns))

    def test_legacy_identity_table_gains_one_provider_identity_per_user_constraint(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE external_identities ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL, "
                "issuer TEXT NOT NULL, subject TEXT NOT NULL)"
            ))
            conn.execute(text(
                "INSERT INTO external_identities "
                "(id, user_id, provider, issuer, subject) "
                "VALUES (1, 7, 'kai', 'https://auth.kai.test', 'subject-1')"
            ))
        self.assertTrue(_ensure_auth_identity_constraints(self.engine))
        self.assertFalse(_ensure_auth_identity_constraints(self.engine))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO external_identities "
                    "(id, user_id, provider, issuer, subject) "
                    "VALUES (2, 7, 'kai', 'https://auth.kai.test', 'subject-2')"
                ))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO external_identities "
                    "(id, user_id, provider, issuer, subject) "
                    "VALUES (3, 8, 'kai', 'https://auth.kai.test', 'subject-1')"
                ))

    def test_legacy_kai_endpoint_issuer_is_normalized_without_changing_account(self):
        original_issuer = settings.KAI_AUTH_ISSUER
        original_endpoint = settings.KAI_AUTH_ENDPOINT_BASE
        settings.KAI_AUTH_ISSUER = "https://auth.kai.test"
        settings.KAI_AUTH_ENDPOINT_BASE = "https://auth.kai.test/api/auth"
        try:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE external_identities ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL, "
                    "issuer TEXT NOT NULL, subject TEXT NOT NULL)"
                ))
                conn.execute(text(
                    "INSERT INTO external_identities VALUES "
                    "(1, 7, 'kai', 'https://auth.kai.test/api/auth', 'subject-1')"
                ))
            self.assertTrue(_normalize_kai_identity_issuers(self.engine))
            self.assertFalse(_normalize_kai_identity_issuers(self.engine))
            with self.engine.begin() as conn:
                row = conn.execute(text(
                    "SELECT user_id, issuer FROM external_identities WHERE id = 1"
                )).one()
            self.assertEqual(row.user_id, 7)
            self.assertEqual(row.issuer, "https://auth.kai.test")
        finally:
            settings.KAI_AUTH_ISSUER = original_issuer
            settings.KAI_AUTH_ENDPOINT_BASE = original_endpoint

    def test_kai_issuer_normalization_stops_on_ambiguous_subject(self):
        original_issuer = settings.KAI_AUTH_ISSUER
        original_endpoint = settings.KAI_AUTH_ENDPOINT_BASE
        settings.KAI_AUTH_ISSUER = "https://auth.kai.test"
        settings.KAI_AUTH_ENDPOINT_BASE = "https://auth.kai.test/api/auth"
        try:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE external_identities ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL, "
                    "issuer TEXT NOT NULL, subject TEXT NOT NULL)"
                ))
                conn.execute(text(
                    "INSERT INTO external_identities VALUES "
                    "(1, 7, 'kai', 'https://auth.kai.test/api/auth', 'same-subject'),"
                    "(2, 8, 'kai', 'https://auth.kai.test', 'same-subject')"
                ))
            with self.assertRaisesRegex(RuntimeError, "migration conflict"):
                _normalize_kai_identity_issuers(self.engine)
        finally:
            settings.KAI_AUTH_ISSUER = original_issuer
            settings.KAI_AUTH_ENDPOINT_BASE = original_endpoint

    def test_duplicate_legacy_bindings_stop_migration_for_manual_resolution(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE external_identities ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL, "
                "issuer TEXT NOT NULL, subject TEXT NOT NULL)"
            ))
            conn.execute(text(
                "INSERT INTO external_identities VALUES "
                "(1, 7, 'kai', 'https://auth.kai.test', 'subject-1'),"
                "(2, 7, 'kai', 'https://auth.kai.test', 'subject-2')"
            ))
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            _ensure_auth_identity_constraints(self.engine)

    def test_duplicate_issuer_subjects_stop_migration_for_manual_resolution(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE external_identities ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL, "
                "issuer TEXT NOT NULL, subject TEXT NOT NULL)"
            ))
            conn.execute(text(
                "INSERT INTO external_identities VALUES "
                "(1, 7, 'kai', 'https://auth.kai.test', 'same-subject'),"
                "(2, 8, 'kai', 'https://auth.kai.test', 'same-subject')"
            ))
        with self.assertRaisesRegex(RuntimeError, "subject conflict"):
            _ensure_auth_identity_constraints(self.engine)

    def test_existing_business_rows_are_backfilled_to_legacy_platform(self):
        attributed = {
            "users": ("created_platform",),
            "payment_orders": ("created_platform", "last_modified_platform"),
            "verifications": ("created_platform", "last_modified_platform"),
            "bank_cards": ("created_platform", "last_modified_platform"),
            "withdrawal_orders": ("created_platform", "last_modified_platform"),
            "posts": ("created_platform", "last_modified_platform"),
            "comments": ("created_platform",),
            "likes": ("created_platform",),
            "follows": ("created_platform",),
            "invite_records": ("created_platform", "last_modified_platform"),
        }
        with self.engine.begin() as conn:
            for table in attributed:
                conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))
                conn.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))
        _ensure_columns(self.engine)
        inspector = inspect(self.engine)
        for table, columns in attributed.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table)}
            self.assertTrue(set(columns).issubset(actual_columns), table)
            with self.engine.begin() as conn:
                row = conn.execute(text(
                    f"SELECT {', '.join(columns)} FROM {table} WHERE id = 1"
                )).one()
            self.assertEqual(tuple(row), tuple("legacy" for _ in columns), table)
            index_names = {index["name"] for index in inspector.get_indexes(table)}
            self.assertIn(f"ix_{table}_created_platform", index_names)


if __name__ == "__main__":
    unittest.main()
