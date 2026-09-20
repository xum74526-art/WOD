"""Durable recovery-mail tests use only synthetic in-memory state."""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import hash_password
from app.core.sensitive import fingerprint, protect, reveal
from app.db.base import Base
from app.integrations import account_email
from app.models import AccountRecoveryMailOutbox, AccountRecoveryToken, User
from app.services import account_recovery as recovery
from app.services import account_recovery_mail as mail_outbox
from app.services.account_deletion_data import scrub_account_data
from app.services.auth_session import utcnow


class AccountRecoveryMailOutboxTests(unittest.TestCase):
    password = "Synthetic-Recovery-Password-42"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.factory()
        names = (
            "SECRET_KEY",
            "SENSITIVE_DATA_KEY",
            "ACCOUNT_RECOVERY_EMAIL_ENABLED",
            "ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN",
            "ACCOUNT_RECOVERY_RESET_TTL_SECONDS",
            "ACCOUNT_RECOVERY_SMTP_HOST",
            "ACCOUNT_RECOVERY_SMTP_PORT",
            "ACCOUNT_RECOVERY_SMTP_USERNAME",
            "ACCOUNT_RECOVERY_SMTP_PASSWORD",
            "ACCOUNT_RECOVERY_SMTP_FROM",
            "ACCOUNT_RECOVERY_SMTP_STARTTLS",
            "ACCOUNT_RECOVERY_SMTP_SSL",
            "ACCOUNT_RECOVERY_MAIL_BATCH_SIZE",
            "ACCOUNT_RECOVERY_MAIL_MAX_ATTEMPTS",
            "ACCOUNT_RECOVERY_MAIL_RETRY_BASE_SECONDS",
            "ACCOUNT_RECOVERY_MAIL_RETRY_MAX_SECONDS",
            "ACCOUNT_RECOVERY_MAIL_LEASE_SECONDS",
            "ACCOUNT_RECOVERY_MAIL_RETENTION_SECONDS",
        )
        self.original_settings = {name: getattr(settings, name) for name in names}
        settings.SECRET_KEY = "synthetic-outbox-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        settings.ACCOUNT_RECOVERY_EMAIL_ENABLED = True
        settings.ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN = "https://web.wod.test"
        settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS = 1800
        settings.ACCOUNT_RECOVERY_SMTP_HOST = "smtp.wod.test"
        settings.ACCOUNT_RECOVERY_SMTP_PORT = 587
        settings.ACCOUNT_RECOVERY_SMTP_USERNAME = ""
        settings.ACCOUNT_RECOVERY_SMTP_PASSWORD = ""
        settings.ACCOUNT_RECOVERY_SMTP_FROM = "no-reply@wod.test"
        settings.ACCOUNT_RECOVERY_SMTP_STARTTLS = True
        settings.ACCOUNT_RECOVERY_SMTP_SSL = False
        settings.ACCOUNT_RECOVERY_MAIL_BATCH_SIZE = 10
        settings.ACCOUNT_RECOVERY_MAIL_MAX_ATTEMPTS = 2
        settings.ACCOUNT_RECOVERY_MAIL_RETRY_BASE_SECONDS = 1
        settings.ACCOUNT_RECOVERY_MAIL_RETRY_MAX_SECONDS = 2
        settings.ACCOUNT_RECOVERY_MAIL_LEASE_SECONDS = 30
        settings.ACCOUNT_RECOVERY_MAIL_RETENTION_SECONDS = 60

    def tearDown(self):
        for name, value in self.original_settings.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    def _verified_user(self, suffix: int = 1) -> User:
        email = f"owner-{suffix}@example.com"
        user = User(
            phone=f"1397000{suffix:04d}",
            username=f"Synthetic mail user {suffix}",
            password=hash_password(self.password),
            account_status="active",
            recovery_email=protect(email),
            recovery_email_fingerprint=fingerprint(email),
            recovery_email_verified_at=utcnow(),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _queued_reset(self) -> tuple[AccountRecoveryMailOutbox, str]:
        user = self._verified_user()
        issued = recovery.request_password_reset(
            self.db, reveal(user.recovery_email)
        )
        self.assertIsNotNone(issued)
        row = self.db.query(AccountRecoveryMailOutbox).one()
        token = reveal(row.token_payload)
        self.assertTrue(token)
        return row, token

    def test_worker_delivers_once_and_erases_encrypted_payload(self):
        queued, token = self._queued_reset()
        recipient = reveal(queued.recipient_payload)

        with patch.object(account_email, "send_account_recovery_email") as sender:
            result = mail_outbox.process_account_recovery_mail_outbox(
                session_factory=self.factory
            )

        self.assertEqual(result, {
            "claimed": 1,
            "delivered": 1,
            "retried": 0,
            "failed": 0,
        })
        sender.assert_called_once_with(
            recovery.PASSWORD_RESET_EMAIL,
            recipient,
            token,
        )
        self.db.expire_all()
        delivered = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(delivered.status, "delivered")
        self.assertEqual(delivered.attempts, 1)
        self.assertIsNotNone(delivered.delivered_at)
        self.assertIsNone(delivered.recipient_payload)
        self.assertIsNone(delivered.token_payload)
        self.assertIsNone(delivered.last_error_code)

    def test_provider_failures_retry_then_fail_without_logging_secrets(self):
        queued, token = self._queued_reset()
        recipient = reveal(queued.recipient_payload)
        with self.assertLogs(mail_outbox.logger, level="WARNING") as captured:
            with patch.object(
                account_email,
                "send_account_recovery_email",
                side_effect=TimeoutError("synthetic provider detail"),
            ):
                first = mail_outbox.process_account_recovery_mail_outbox(
                    session_factory=self.factory
                )
        self.assertEqual(first["retried"], 1)
        logs = " ".join(captured.output)
        self.assertNotIn(recipient, logs)
        self.assertNotIn(token, logs)
        self.assertNotIn("synthetic provider detail", logs)

        self.db.expire_all()
        retrying = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(retrying.status, "retry")
        self.assertEqual(retrying.attempts, 1)
        self.assertEqual(retrying.last_error_code, "TimeoutError")
        self.assertTrue(retrying.recipient_payload.startswith("enc:v1:"))
        retrying.available_at = utcnow() - timedelta(seconds=1)
        self.db.commit()

        with patch.object(
            account_email,
            "send_account_recovery_email",
            side_effect=ConnectionError("must not be persisted"),
        ):
            second = mail_outbox.process_account_recovery_mail_outbox(
                session_factory=self.factory
            )
        self.assertEqual(second["failed"], 1)
        self.db.expire_all()
        failed = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.attempts, 2)
        self.assertEqual(failed.last_error_code, "ConnectionError")
        self.assertIsNone(failed.recipient_payload)
        self.assertIsNone(failed.token_payload)

    def test_consumed_token_cancels_mail_without_contacting_provider(self):
        queued, _token = self._queued_reset()
        token_row = self.db.get(AccountRecoveryToken, queued.recovery_token_id)
        token_row.consumed_at = utcnow()
        self.db.commit()

        with patch.object(account_email, "send_account_recovery_email") as sender:
            result = mail_outbox.process_account_recovery_mail_outbox(
                session_factory=self.factory
            )

        sender.assert_not_called()
        self.assertEqual(result["delivered"], 0)
        self.db.expire_all()
        canceled = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertEqual(canceled.last_error_code, "invalid_or_stale_payload")
        self.assertIsNone(canceled.recipient_payload)
        self.assertIsNone(canceled.token_payload)
        token_row = self.db.get(AccountRecoveryToken, queued.recovery_token_id)
        self.assertIsNone(token_row.target_email)
        self.assertIsNone(token_row.target_email_fingerprint)

        canceled.finished_at = utcnow() - timedelta(seconds=61)
        token_row.consumed_at = utcnow() - timedelta(seconds=61)
        mail_id = canceled.id
        token_id = token_row.id
        self.db.commit()
        mail_outbox.process_account_recovery_mail_outbox(
            session_factory=self.factory
        )
        self.db.expire_all()
        self.assertIsNone(self.db.get(AccountRecoveryMailOutbox, mail_id))
        self.assertIsNone(self.db.get(AccountRecoveryToken, token_id))

    def test_compare_and_swap_claim_is_exclusive_and_stale_lease_recovers(self):
        queued, _token = self._queued_reset()
        first = mail_outbox._claim_one(self.factory, utcnow())
        second = mail_outbox._claim_one(self.factory, utcnow())

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.db.expire_all()
        leased = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(leased.status, "sending")
        self.assertEqual(leased.attempts, 1)
        leased.locked_at = utcnow() - timedelta(seconds=121)
        self.db.commit()

        with patch.object(account_email, "send_account_recovery_email") as sender:
            result = mail_outbox.process_account_recovery_mail_outbox(
                session_factory=self.factory
            )

        sender.assert_called_once()
        self.assertEqual(result["delivered"], 1)
        self.db.expire_all()
        recovered = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(recovered.status, "delivered")
        self.assertEqual(recovered.attempts, 2)

    def test_stale_snapshot_cannot_reclaim_another_workers_live_lease(self):
        queued, _token = self._queued_reset()
        first_session = self.factory()
        self.addCleanup(first_session.close)
        snapshot = first_session.query(
            AccountRecoveryMailOutbox.id,
            AccountRecoveryMailOutbox.status,
            AccountRecoveryMailOutbox.attempts,
        ).filter(AccountRecoveryMailOutbox.id == queued.id).one()

        second_worker_claim = mail_outbox._claim_one(self.factory, utcnow())
        self.assertIsNotNone(second_worker_claim)
        reclaimed = mail_outbox._try_claim_snapshot(
            first_session,
            job_id=snapshot.id,
            prior_status=snapshot.status,
            prior_attempts=snapshot.attempts,
            now=utcnow(),
        )
        first_session.rollback()

        self.assertFalse(reclaimed)
        self.db.expire_all()
        leased = self.db.get(AccountRecoveryMailOutbox, queued.id)
        self.assertEqual(leased.status, "sending")
        self.assertEqual(leased.attempts, 1)

    def test_unknown_address_row_is_suppressed_and_eventually_purged(self):
        self.assertIsNone(
            recovery.request_password_reset(self.db, "unknown@example.com")
        )
        row = self.db.query(AccountRecoveryMailOutbox).one()
        self.assertEqual(row.status, "suppressed")
        self.assertIsNone(row.user_id)
        self.assertIsNone(row.recovery_token_id)
        self.assertIsNone(row.recipient_payload)
        self.assertIsNone(row.token_payload)
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

        row.finished_at = utcnow() - timedelta(seconds=61)
        self.db.commit()
        with patch.object(account_email, "send_account_recovery_email") as sender:
            mail_outbox.process_account_recovery_mail_outbox(
                session_factory=self.factory
            )
        sender.assert_not_called()
        self.assertEqual(self.db.query(AccountRecoveryMailOutbox).count(), 0)

    def test_account_scrub_removes_pending_mail_before_its_token(self):
        queued, _token = self._queued_reset()
        user = self.db.get(User, queued.user_id)

        scrub_account_data(self.db, user)
        self.db.commit()

        self.assertEqual(self.db.query(AccountRecoveryMailOutbox).count(), 0)
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)


if __name__ == "__main__":
    unittest.main()
