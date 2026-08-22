import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import User  # noqa: F401
from init_db import _migrate_unverified_phone_flags


class PhoneBindingMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

    def test_unsafe_legacy_true_values_are_demoted_exactly_once(self):
        with self.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (username, phone, phone_bound, password, role, supplier_status) "
                "VALUES ('legacy', '13900000071', TRUE, '!', 'personal', 'none')"
            ))

        self.assertTrue(_migrate_unverified_phone_flags(self.engine))
        with self.engine.begin() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT phone_bound FROM users WHERE phone='13900000071'"
            )).scalar(), 0)
            # A later real verification must survive future init_db runs.
            conn.execute(text(
                "UPDATE users SET phone_bound = TRUE WHERE phone='13900000071'"
            ))

        self.assertFalse(_migrate_unverified_phone_flags(self.engine))
        with self.engine.begin() as conn:
            self.assertEqual(conn.execute(text(
                "SELECT phone_bound FROM users WHERE phone='13900000071'"
            )).scalar(), 1)


if __name__ == "__main__":
    unittest.main()
