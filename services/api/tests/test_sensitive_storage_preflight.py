import asyncio
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import init_db
from app.core.config import DEFAULT_SECRET_KEY, settings
from app.core.sensitive import (
    SensitiveDataDecryptionError,
    assert_sensitive_storage_secure,
    fingerprint,
    protect,
    reveal,
)
from app.db.base import Base
from app.models.bank_card import BankCard
from app.models.user import User
from app.models.verification import Verification
from app.models.wallet import Wallet


REPOSITORY = Path(__file__).resolve().parents[3]


def legacy_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def legacy_protect(value: str, secret: str) -> str:
    token = Fernet(legacy_key(secret)).encrypt(value.encode("utf-8")).decode("ascii")
    return "enc:v1:" + token


class SensitiveStoragePreflightTests(unittest.TestCase):
    def setUp(self):
        self.original_secret = settings.SECRET_KEY
        self.original_sensitive_key = settings.SENSITIVE_DATA_KEY
        self.original_capabilities = {
            name: getattr(settings, name)
            for name in (
                "ID_OCR_ENABLED",
                "MANUAL_BANK_CARD_ENABLED",
                "MANUAL_PAYOUT_ENABLED",
                "ACCOUNT_RECOVERY_EMAIL_ENABLED",
            )
        }
        for name in self.original_capabilities:
            setattr(settings, name, False)

    def tearDown(self):
        settings.SECRET_KEY = self.original_secret
        settings.SENSITIVE_DATA_KEY = self.original_sensitive_key
        for name, value in self.original_capabilities.items():
            setattr(settings, name, value)

    def configure_valid_keys(self) -> bytes:
        settings.SECRET_KEY = "unit-test-stable-application-secret"
        key = Fernet.generate_key()
        settings.SENSITIVE_DATA_KEY = key.decode("ascii")
        return key

    def test_storage_preflight_is_unconditional_and_writers_fail_closed(self):
        settings.SECRET_KEY = DEFAULT_SECRET_KEY
        settings.SENSITIVE_DATA_KEY = ""

        with self.assertRaisesRegex(RuntimeError, "default_secret_key"):
            assert_sensitive_storage_secure()
        with self.assertRaisesRegex(RuntimeError, "missing_sensitive_data_key"):
            protect("must-not-be-persisted")
        with self.assertRaisesRegex(RuntimeError, "missing_sensitive_data_key"):
            fingerprint("must-not-be-persisted")

        settings.SECRET_KEY = "independence-test-secret"
        settings.SENSITIVE_DATA_KEY = legacy_key(settings.SECRET_KEY).decode("ascii")
        with self.assertRaisesRegex(RuntimeError, "sensitive_data_key_not_independent"):
            assert_sensitive_storage_secure()
        with self.assertRaisesRegex(RuntimeError, "sensitive_data_key_not_independent"):
            protect("must-not-use-derived-key")

    def test_storage_preflight_rejects_exact_secret_key_reuse(self):
        reused_fernet_secret = Fernet.generate_key().decode("ascii")
        settings.SECRET_KEY = f"  {reused_fernet_secret}  "
        settings.SENSITIVE_DATA_KEY = reused_fernet_secret

        with self.assertRaisesRegex(RuntimeError, "sensitive_data_key_not_independent"):
            assert_sensitive_storage_secure()

    def test_storage_preflight_rejects_public_default_derived_key(self):
        settings.SECRET_KEY = "current-non-default-secret"
        settings.SENSITIVE_DATA_KEY = legacy_key(DEFAULT_SECRET_KEY).decode("ascii")

        with self.assertRaisesRegex(RuntimeError, "sensitive_data_key_not_independent"):
            assert_sensitive_storage_secure()

    def test_legacy_secret_derived_ciphertext_is_read_and_reencrypted(self):
        settings.SECRET_KEY = "stable-legacy-secret-needed-for-transition"
        primary_key = Fernet.generate_key()
        settings.SENSITIVE_DATA_KEY = primary_key.decode("ascii")
        legacy_value = legacy_protect("6222021234567890", settings.SECRET_KEY)

        self.assertEqual(reveal(legacy_value), "6222021234567890")
        reencrypted = protect(legacy_value)

        self.assertNotEqual(reencrypted, legacy_value)
        token = reencrypted.removeprefix("enc:v1:").encode("ascii")
        self.assertEqual(
            Fernet(primary_key).decrypt(token).decode("utf-8"),
            "6222021234567890",
        )

    def test_source_default_legacy_ciphertext_can_only_be_migrated_to_primary_key(self):
        settings.SECRET_KEY = "current-stable-non-default-secret"
        primary_key = Fernet.generate_key()
        settings.SENSITIVE_DATA_KEY = primary_key.decode("ascii")
        legacy_value = legacy_protect("historical-value", DEFAULT_SECRET_KEY)

        reencrypted = protect(legacy_value)

        self.assertNotEqual(reencrypted, legacy_value)
        self.assertEqual(reveal(reencrypted), "historical-value")

    def test_unreadable_ciphertext_never_becomes_an_empty_value(self):
        self.configure_valid_keys()
        malformed = "enc:v1:not-a-valid-fernet-token"

        with self.assertRaises(SensitiveDataDecryptionError):
            reveal(malformed)
        with self.assertRaises(SensitiveDataDecryptionError):
            protect(malformed)

    def test_invalid_keys_leave_database_file_byte_for_byte_unchanged(self):
        cases = {
            "empty": ("non-default-but-stable-secret", ""),
            "derived": (
                "non-default-derived-secret",
                legacy_key("non-default-derived-secret").decode("ascii"),
            ),
        }
        guarded_calls = (
            lambda db_engine: init_db.init(),
            lambda db_engine: init_db._migrate_sensitive_fields(),
            lambda db_engine: init_db._migrate_manual_payout_fields(db_engine),
        )

        for case_name, (secret, sensitive_key) in cases.items():
            for call_index, guarded_call in enumerate(guarded_calls):
                with self.subTest(case=case_name, call=call_index), tempfile.TemporaryDirectory() as temp:
                    database = Path(temp) / "guarded.sqlite3"
                    db_engine = create_engine(f"sqlite:///{database}")
                    with db_engine.begin() as connection:
                        connection.execute(text("CREATE TABLE sentinel (value TEXT NOT NULL)"))
                        connection.execute(text("INSERT INTO sentinel (value) VALUES ('unchanged')"))
                    db_engine.dispose()
                    before = database.read_bytes()

                    guarded_engine = create_engine(f"sqlite:///{database}")
                    settings.SECRET_KEY = secret
                    settings.SENSITIVE_DATA_KEY = sensitive_key
                    with patch.object(init_db, "engine", guarded_engine):
                        with self.assertRaises(RuntimeError):
                            guarded_call(guarded_engine)
                    guarded_engine.dispose()

                    self.assertEqual(database.read_bytes(), before)

    def test_valid_key_migrates_plaintext_and_legacy_ciphertext(self):
        self.configure_valid_keys()
        legacy_ciphertext = legacy_protect("6222021234567890", settings.SECRET_KEY)
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(
                phone="13900009991",
                username="migration",
                password="!",
                recovery_email=legacy_protect("owner@example.com", settings.SECRET_KEY),
                recovery_email_fingerprint="legacy-fingerprint",
            )
            db.add(user)
            db.flush()
            card = BankCard(
                user_id=user.id,
                bank_name="test",
                card_number=legacy_ciphertext,
                holder="tester",
                phone="13900009991",
            )
            verification = Verification(
                user_id=user.id,
                real_name="tester",
                id_card=legacy_protect("110101199001011111", settings.SECRET_KEY),
                ocr_summary=legacy_protect('{"status":"legacy"}', settings.SECRET_KEY),
                status="pending",
            )
            db.add_all([card, verification])
            db.commit()

            init_db._migrate_sensitive_fields(db)
            db.refresh(card)

            self.assertNotEqual(card.card_number, legacy_ciphertext)
            self.assertEqual(reveal(card.card_number), "6222021234567890")
            self.assertTrue(card.phone.startswith("enc:v1:"))
            self.assertEqual(reveal(card.phone), "13900009991")
            self.assertEqual(reveal(user.recovery_email), "owner@example.com")
            self.assertEqual(
                user.recovery_email_fingerprint,
                fingerprint("owner@example.com"),
            )
            self.assertEqual(reveal(verification.id_card), "110101199001011111")
            self.assertEqual(reveal(verification.ocr_summary), '{"status":"legacy"}')
        engine.dispose()

    def test_manual_payout_migration_rolls_back_on_unreadable_card(self):
        self.configure_valid_keys()
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(phone="13900009992", username="rollback", password="!")
            db.add(user)
            db.flush()
            wallet = Wallet(user_id=user.id, balance=0, frozen=0)
            valid_card = BankCard(
                user_id=user.id,
                bank_name="test-valid",
                card_number="4539578763621486",
                holder="tester",
                phone=protect("13900009992"),
                status="active",
                verification_mode="manual_review",
                is_default=True,
            )
            unreadable_card = BankCard(
                user_id=user.id,
                bank_name="test-unreadable",
                card_number="enc:v1:unreadable",
                holder="tester",
                phone=protect("13900009992"),
                status="registered",
                verification_mode="format_only",
                is_default=False,
            )
            db.add_all([wallet, valid_card, unreadable_card])
            db.commit()

            with self.assertRaises(SensitiveDataDecryptionError):
                init_db._migrate_manual_payout_fields(engine, db)
            db.expire_all()

            self.assertEqual(valid_card.status, "active")
            self.assertEqual(valid_card.verification_mode, "manual_review")
            self.assertTrue(valid_card.is_default)
            self.assertIsNone(valid_card.card_fingerprint)
            self.assertEqual(valid_card.card_number, "4539578763621486")
            self.assertEqual(unreadable_card.status, "registered")
            self.assertFalse(unreadable_card.is_default)
            self.assertEqual(unreadable_card.card_number, "enc:v1:unreadable")
        engine.dispose()

    def test_api_lifespan_rejects_invalid_storage_with_capabilities_off(self):
        from app.main import lifespan

        settings.SECRET_KEY = "non-default-secret"
        settings.SENSITIVE_DATA_KEY = ""

        async def exercise() -> None:
            async with lifespan(None):
                self.fail("lifespan must not start")

        with self.assertRaisesRegex(RuntimeError, "missing_sensitive_data_key"):
            asyncio.run(exercise())

    def test_deployment_entrypoints_run_read_only_preflight_first(self):
        service = (REPOSITORY / "infra" / "kai-api.service").read_text(encoding="utf-8")
        entrypoint = (REPOSITORY / "services" / "api" / "docker-entrypoint.sh").read_text(
            encoding="utf-8"
        )
        dockerfile = (REPOSITORY / "services" / "api" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        preflight = (
            REPOSITORY / "services" / "api" / "preflight_sensitive_storage.py"
        ).read_text(encoding="utf-8")

        for name, content in (("systemd", service), ("docker", entrypoint)):
            with self.subTest(entrypoint=name):
                preflight_position = content.index("preflight_sensitive_storage.py")
                self.assertLess(preflight_position, content.index("migrate_account_recovery.py"))
                self.assertLess(preflight_position, content.index("init_db.py"))

        self.assertIn(
            "COPY preflight_sensitive_storage.py ./preflight_sensitive_storage.py",
            dockerfile,
        )
        self.assertNotIn("sqlalchemy", preflight.lower())
        self.assertNotIn("app.db", preflight)
        self.assertNotIn("DATABASE_URL", preflight)


if __name__ == "__main__":
    unittest.main()
