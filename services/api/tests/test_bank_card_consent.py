import unittest
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import BankCard, User, Verification
from app.routers import bank_card as bank_card_router
from app.schemas.bank_card import BankCardIn
from app.utils.response import BizError
import init_db


VALID_CARD = "4539578763621486"


class BankCardConsentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(phone="13900002001", username="银行卡同意测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.db.add(Verification(
            user_id=self.user.id,
            real_name="张三",
            id_card="11010519491231002X",
            status="verified",
        ))
        self.db.commit()

        self.original = {
            "MANUAL_BANK_CARD_ENABLED": settings.MANUAL_BANK_CARD_ENABLED,
            "SECRET_KEY": settings.SECRET_KEY,
            "SENSITIVE_DATA_KEY": settings.SENSITIVE_DATA_KEY,
        }
        settings.MANUAL_BANK_CARD_ENABLED = True
        settings.SECRET_KEY = "unit-test-bank-card-consent-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def payload(*, sensitive_consent: bool = True, **extra):
        values = dict(
            bank_name="测试银行",
            card_number=VALID_CARD,
            holder="张三",
            phone="13900002001",
            sensitive_consent=sensitive_consent,
        )
        values.update(extra)
        return BankCardIn(**values)

    def test_input_requires_explicit_strict_consent_and_rejects_client_audit_fields(self):
        with self.assertRaises(ValidationError):
            BankCardIn(
                bank_name="测试银行",
                card_number=VALID_CARD,
                holder="张三",
                phone="13900002001",
            )
        with self.assertRaises(ValidationError):
            BankCardIn(
                bank_name="测试银行",
                card_number=VALID_CARD,
                holder="张三",
                phone="13900002001",
                sensitive_consent=1,
            )
        with self.assertRaises(ValidationError):
            BankCardIn(
                bank_name="测试银行",
                card_number=VALID_CARD,
                holder="张三",
                phone="13900002001",
                sensitive_consent=True,
                consent_at="2000-01-01T00:00:00Z",
                consent_version="client-forged",
            )

    def test_false_consent_is_rejected_without_creating_a_card(self):
        with self.assertRaisesRegex(BizError, "单独同意") as raised:
            bank_card_router.add_card(
                self.payload(sensitive_consent=False),
                self.user,
                self.db,
                "web",
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.db.query(BankCard).count(), 0)

    def test_server_records_timestamp_and_version_but_only_returns_public_evidence(self):
        before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        result = bank_card_router.add_card(
            self.payload(),
            self.user,
            self.db,
            "ios",
        )["data"]
        after = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=1)

        row = self.db.query(BankCard).filter(BankCard.id == result["id"]).one()
        self.assertGreaterEqual(row.consent_at, before)
        self.assertLessEqual(row.consent_at, after)
        self.assertEqual(
            row.consent_version,
            bank_card_router.BANK_CARD_SENSITIVE_CONSENT_VERSION,
        )
        self.assertTrue(result["consent_recorded"])
        self.assertEqual(result["consent_version"], row.consent_version)
        self.assertNotIn("consent_at", result)

    def test_historical_card_reports_no_record_without_exposing_a_timestamp(self):
        legacy = BankCard(
            user_id=self.user.id,
            bank_name="历史银行",
            card_number=VALID_CARD,
            holder="张三",
            status="registered",
            verification_mode="format_only",
        )
        self.db.add(legacy)
        self.db.commit()

        result = bank_card_router._card_out(legacy)
        self.assertFalse(result["consent_recorded"])
        self.assertIsNone(result["consent_version"])
        self.assertNotIn("consent_at", result)

    def test_explicit_resubmission_upgrades_one_historical_card_in_place(self):
        legacy = BankCard(
            user_id=self.user.id,
            bank_name="历史银行",
            card_number=VALID_CARD,
            holder="张三",
            phone="13900002001",
            status="active",
            verification_mode="legacy_unvalidated",
            is_default=True,
        )
        self.db.add(legacy)
        self.db.commit()

        result = bank_card_router.add_card(
            self.payload(bank_name="更新银行"),
            self.user,
            self.db,
            "android",
        )["data"]

        self.assertEqual(result["id"], legacy.id)
        self.assertTrue(result["consent_recorded"])
        self.assertEqual(self.db.query(BankCard).count(), 1)
        self.db.refresh(legacy)
        self.assertEqual(
            legacy.consent_version,
            bank_card_router.BANK_CARD_SENSITIVE_CONSENT_VERSION,
        )
        self.assertEqual(legacy.verification_mode, "format_only")

    def test_outdated_consent_version_is_not_reported_as_current(self):
        legacy = BankCard(
            user_id=self.user.id,
            bank_name="历史银行",
            card_number=VALID_CARD,
            holder="张三",
            consent_at=datetime(2025, 1, 1),
            consent_version="bank-card-sensitive-v0",
        )
        self.assertFalse(bank_card_router._card_out(legacy)["consent_recorded"])

    def test_legacy_schema_migration_adds_consent_audit_columns_idempotently(self):
        legacy_engine = create_engine("sqlite://")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE bank_cards (id INTEGER PRIMARY KEY)"
                ))
            init_db._ensure_columns(legacy_engine)
            init_db._ensure_columns(legacy_engine)

            columns = {
                item["name"]: item
                for item in inspect(legacy_engine).get_columns("bank_cards")
            }
            self.assertIn("consent_at", columns)
            self.assertIn("consent_version", columns)
            self.assertEqual(columns["consent_version"]["type"].length, 64)
        finally:
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
