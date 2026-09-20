"""Deletion tests use synthetic users and isolated SQLite/upload directories only."""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_auth_context
from app.core.security import create_access_token, hash_password, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.models import (
    AccountDeletionRequest, AccountRecoveryToken, AuthSession, ExternalIdentity,
    User, Wallet, Supplier, Product, Order, InviteRecord, RewardAccrual,
)
from app.routers import account_deletion as router
from app.services import account_deletion as service
from app.services.auth_session import create_authenticated_session, utcnow
from app.services.notification_service import create_notification
from app.utils.response import BizError, error
from init_db import _ensure_columns


class AccountDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "SyntheticPassword-42"
        cls.hashed = hash_password(cls.password)

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def enable_fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.factory()
        self.user = User(username="Synthetic user", phone="13900009901", password=self.hashed)
        self.other = User(username="Unrelated user", phone="13900009902", password=self.hashed)
        self.db.add_all([self.user, self.other])
        self.db.commit()
        self.db.add(Wallet(user_id=self.user.id, balance=0, frozen=0))
        self.db.commit()
        self.temp = tempfile.TemporaryDirectory(prefix="wod-deletion-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def ticket(self):
        return service.verify_deletion_password(self.db, self.user, self.password)["ticket"]

    def row(self, ticket):
        return self.db.query(AccountDeletionRequest).filter_by(ticket_hash=service._digest(ticket)).one()

    def test_verification_is_not_deletion_and_only_stores_hash(self):
        ticket = self.ticket()
        self.assertEqual(self.user.account_status, "active")
        row = self.row(ticket)
        self.assertNotEqual(row.ticket_hash, ticket)
        self.assertNotIn(self.password, repr(row.__dict__))
        self.assertEqual(row.status, "verified")
        self.assertFalse(service.deletion_status(self.db, ticket)["blockers"])

    def test_bad_password_does_not_issue_capability(self):
        with self.assertRaisesRegex(BizError, "KAI星算账号密码"):
            service.verify_deletion_password(self.db, self.user, "incorrect")
        self.assertEqual(self.db.query(AccountDeletionRequest).count(), 0)

    def test_kai_only_account_uses_fresh_single_use_reauth_proof(self):
        self.user.password = "!"
        self.db.add(ExternalIdentity(
            user_id=self.user.id,
            provider="kai",
            issuer="",
            subject="kai-only-user",
        ))
        self.db.commit()
        proof = service.issue_kai_reauth_token(self.db, self.user)
        with patch("app.services.kai_auth.is_configured", return_value=True):
            eligibility = service.eligibility(self.db, self.user)
            self.assertEqual(eligibility["verification_methods"], ["kai"])
            verification = service.verify_deletion_kai(self.db, self.user, proof)
        self.assertEqual(self.row(verification["ticket"]).status, "verified")
        token_row = self.db.query(AccountRecoveryToken).filter_by(
            purpose=service.KAI_DELETION_REAUTH,
        ).one()
        self.assertIsNotNone(token_row.consumed_at)
        with (
            patch("app.services.kai_auth.is_configured", return_value=True),
            self.assertRaisesRegex(BizError, "无效或已过期"),
        ):
            service.verify_deletion_kai(self.db, self.user, proof)

    def test_kai_deletion_proof_is_bound_to_user_and_cannot_reset_password(self):
        self.user.password = "!"
        self.db.add(ExternalIdentity(
            user_id=self.user.id,
            provider="kai",
            issuer="",
            subject="kai-only-user",
        ))
        self.db.commit()
        proof = service.issue_kai_reauth_token(self.db, self.user)
        with (
            patch("app.services.kai_auth.is_configured", return_value=True),
            self.assertRaisesRegex(BizError, "无效或已过期"),
        ):
            service.verify_deletion_kai(self.db, self.other, proof)
        from app.services import account_recovery
        with self.assertRaisesRegex(BizError, account_recovery.INVALID_TOKEN_MESSAGE):
            account_recovery.reset_password(self.db, proof, "Replacement-password-42")
        with patch("app.services.kai_auth.is_configured", return_value=True):
            verification = service.verify_deletion_kai(self.db, self.user, proof)
        self.assertTrue(verification["ticket"])

    def test_kai_reauth_proof_is_invalidated_by_auth_version_change(self):
        self.user.password = "!"
        self.db.add(ExternalIdentity(
            user_id=self.user.id,
            provider="kai",
            issuer="",
            subject="kai-only-user",
        ))
        self.db.commit()
        proof = service.issue_kai_reauth_token(self.db, self.user)
        self.user.auth_version += 1
        self.db.commit()
        with (
            patch("app.services.kai_auth.is_configured", return_value=True),
            self.assertRaisesRegex(BizError, "无效或已过期"),
        ):
            service.verify_deletion_kai(self.db, self.user, proof)

    def test_explicit_confirmation_required(self):
        ticket = self.ticket()
        with self.assertRaises(BizError):
            service.submit_deletion(self.db, ticket, False)
        self.assertEqual(self.user.account_status, "active")

    def test_rechecks_balances_after_verification(self):
        ticket = self.ticket()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user.id).one()
        wallet.balance = Decimal("1.000001")
        self.db.commit()
        result = service.submit_deletion(self.db, ticket, True)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("wallet_not_empty", [b["code"] for b in result["blockers"]])
        self.assertEqual(wallet.balance, Decimal("1.000001"))
        self.assertEqual(self.user.account_status, "active")

    def test_password_change_invalidates_old_proof(self):
        ticket = self.ticket()
        self.user.password = hash_password("replacement-password")
        self.db.commit()
        with self.assertRaises(BizError):
            service.submit_deletion(self.db, ticket, True)

    def test_expired_verification_allows_status_but_not_submit(self):
        ticket = self.ticket()
        self.row(ticket).expires_at = utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.assertEqual(service.deletion_status(self.db, ticket)["status"], "verified")
        with self.assertRaises(BizError):
            service.submit_deletion(self.db, ticket, True)

    def test_acceptance_revokes_all_sessions_including_legacy_jwt(self):
        tokens = [create_access_token(self.user.id)]
        for platform in ("web", "android", "ios"):
            issued = create_authenticated_session(self.db, self.user, platform=platform, client_id=platform, auth_method="password")
            tokens.append(issued.token)
        ticket = self.ticket()
        self.assertEqual(service.submit_deletion(self.db, ticket, True)["status"], "processing")
        self.assertEqual(self.db.query(AuthSession).filter_by(user_id=self.user.id, revoked_at=None).count(), 0)
        for token in tokens:
            with self.assertRaises(BizError):
                get_current_auth_context(token=token, db=self.db)
        with self.assertRaises(BizError):
            create_authenticated_session(self.db, self.user, platform="android", client_id="android", auth_method="kai_oidc")

    def test_cleanup_completed_only_after_files_removed_and_unrelated_user_unchanged(self):
        (self.root / "avatars").mkdir()
        owned = self.root / "avatars" / f"avatar_{self.user.id}.png"
        unrelated = self.root / "avatars" / f"avatar_{self.other.id}.png"
        owned.write_bytes(b"synthetic owned image")
        unrelated.write_bytes(b"synthetic unrelated image")
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        request_id = self.row(ticket).id
        self.assertTrue(service.process_deletion(self.db, request_id, root=self.root))
        self.assertFalse(owned.exists())
        self.assertEqual(unrelated.read_bytes(), b"synthetic unrelated image")
        self.db.refresh(self.user)
        self.db.refresh(self.other)
        self.assertEqual(self.user.account_status, "deleted")
        self.assertIsNotNone(self.user.deleted_at)
        self.assertFalse(verify_password(self.password, self.user.password))
        self.assertEqual(self.other.phone, "13900009902")
        self.assertEqual(self.other.account_status, "active")
        self.assertEqual(service.deletion_status(self.db, ticket)["status"], "completed")
        self.assertEqual(service.submit_deletion(self.db, ticket, True)["status"], "completed")
        self.assertTrue(service.process_deletion(self.db, request_id, root=self.root))
        self.assertEqual(self.db.execute(text("PRAGMA foreign_key_check")).all(), [])

    def test_failure_after_db_scrub_remains_processing_and_resumes(self):
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        row = self.row(ticket)
        with patch.object(Path, "unlink", side_effect=PermissionError("private data must not be logged")):
            self.assertFalse(service.process_deletion(self.db, row.id, root=self.root))
        self.db.refresh(row)
        self.assertEqual(row.status, "processing")
        self.assertEqual(row.last_error_code, "cleanup_retry_required")
        self.assertIsNotNone(row.data_scrubbed_at)
        self.assertIsNone(row.completed_at)
        self.assertTrue(service.process_deletion(self.db, row.id, root=self.root))

    def test_worker_rechecks_late_obligations_before_scrubbing_identity(self):
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        self.db.query(Wallet).filter_by(user_id=self.user.id).update({Wallet.balance: Decimal("2")})
        self.db.commit()
        row = self.row(ticket)
        self.assertFalse(service.process_deletion(self.db, row.id, root=self.root))
        self.assertEqual(row.last_error_code, "obligations_require_review")
        self.assertIsNone(row.data_scrubbed_at)
        self.assertEqual(self.user.phone, "13900009901")
        self.assertTrue(service.deletion_status(self.db, ticket)["blockers"])

    def test_scoped_cleanup_rejects_traversal_absolute_and_other_user(self):
        for relative in ("../secret", "D:/secret", "avatars/avatar_999.png", "community/999/" + "a" * 32 + ".jpg"):
            with self.assertRaises(ValueError):
                service._owned_path(self.root, relative, self.user.id)
        owned_mov = f"community/{self.user.id}/" + "a" * 32 + ".mov"
        self.assertEqual(service._owned_path(self.root, owned_mov, self.user.id), self.root / owned_mov)

    def test_windows_junction_inside_root_is_rejected(self):
        relative = f"community/{self.user.id}/" + "a" * 32 + ".png"
        with patch.object(Path, "is_junction", return_value=True, create=True):
            with self.assertRaises(ValueError):
                service._owned_path(self.root, relative, self.user.id)

    def test_symlink_below_upload_root_is_rejected(self):
        relative = f"community/{self.user.id}/" + "a" * 32 + ".png"
        with tempfile.TemporaryDirectory(prefix="wod-deletion-escape-") as escaped:
            (self.root / "community").symlink_to(Path(escaped), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink_cleanup_path"):
                service._owned_path(self.root, relative, self.user.id)

    def test_privileged_blocker_survives_status_query(self):
        self.user.role = "admin"
        self.db.commit()
        ticket = self.ticket()
        self.assertEqual(service.submit_deletion(self.db, ticket, True)["status"], "blocked")
        self.assertIn("privileged_account", [b["code"] for b in service.deletion_status(self.db, ticket)["blockers"]])

    def test_new_registration_uses_new_id_and_does_not_reactivate_tombstone(self):
        original_id = self.user.id
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        self.assertTrue(service.process_deletion(self.db, self.row(ticket).id, root=self.root))
        fresh = User(username="New registration", phone="13900009901", password=self.hashed)
        self.db.add(fresh)
        self.db.commit()
        self.assertNotEqual(fresh.id, original_id)
        self.assertEqual(self.db.get(User, original_id).account_status, "deleted")
        self.assertEqual(fresh.account_status, "active")

    def test_deleted_inviter_cannot_get_new_v2_qualification_or_commission(self):
        from app.services import invite_rewards_v2 as invites
        record = InviteRecord(inviter_id=self.user.id, invitee_id=self.other.id,
                              invitee_phone=self.other.phone, qualification_policy_version=invites.INVITE_V2_RELATIONSHIP_VERSION,
                              qualification_status=invites.STATUS_QUALIFIED, qualified_at=utcnow() - timedelta(days=1))
        self.db.add(record)
        self.db.commit()
        self.user.account_status = "deleted"
        self.db.commit()
        with patch.object(invites, "invite_v2_enabled", return_value=True):
            self.assertEqual(invites.reevaluate_invitee_qualification(self.other.id, self.db).qualification_status, invites.STATUS_QUALIFIED)
        result = invites._create_commission(record, source_type="order", source_id=12345,
                                           order=None, renewal=None, event_at=utcnow(), db=self.db)
        self.assertIsNone(result)
        self.assertEqual(self.db.query(RewardAccrual).count(), 0)

    def test_another_preissued_ticket_cannot_start_second_job(self):
        first, second = self.ticket(), self.ticket()
        service.submit_deletion(self.db, first, True)
        with self.assertRaises(BizError):
            service.submit_deletion(self.db, second, True)
        self.assertEqual(self.db.query(AccountDeletionRequest).filter_by(status="processing").count(), 1)

    def test_old_authenticated_transaction_cannot_commit_after_deletion(self):
        token = create_access_token(self.user.id)
        stale = self.factory()
        try:
            stale_user = get_current_auth_context(token=token, db=stale).user
            stale.commit()
            ticket = self.ticket()
            service.submit_deletion(self.db, ticket, True)
            stale_user.username = "should not persist"
            with self.assertRaises(BizError):
                stale.commit()
            stale.rollback()
        finally:
            stale.close()

    def test_other_buyer_cannot_create_order_for_deleted_supplier(self):
        supplier = Supplier(user_id=self.user.id, company_name="Synthetic", contact="Synthetic", phone="13900009901")
        self.db.add(supplier)
        self.db.flush()
        product = Product(name="Synthetic", gpu_model="H100", memory="80GB", supplier_id=supplier.id, price=1)
        self.db.add(product)
        self.db.commit()
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        other_db = self.factory()
        try:
            other_db.add(Order(order_no="synthetic-racing-order", user_id=self.other.id, product_id=product.id, amount=1))
            with self.assertRaises(BizError):
                other_db.commit()
            other_db.rollback()
        finally:
            other_db.close()

    def test_notification_job_does_not_recreate_deleted_inbox(self):
        ticket = self.ticket()
        service.submit_deletion(self.db, ticket, True)
        self.assertIsNone(create_notification(self.db, user_id=self.user.id, title="historical notification"))

    def test_legacy_migration_adds_only_account_fields_without_changing_credentials(self):
        legacy = create_engine("sqlite://")
        try:
            with legacy.begin() as conn:
                conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, phone TEXT, password TEXT)"))
                conn.execute(text("INSERT INTO users VALUES (1, 'Synthetic', '13900009999', 'unchanged')"))
            _ensure_columns(legacy)
            _ensure_columns(legacy)
            with legacy.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT phone,password,account_status,deleted_at FROM users")).one(), ("13900009999", "unchanged", "active", None))
        finally:
            legacy.dispose()

    def test_http_capability_flow_and_strict_confirmation(self):
        app = FastAPI()
        app.include_router(router.router)
        @app.exception_handler(BizError)
        async def on_error(_request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg))
        def db_override():
            yield self.db
        app.dependency_overrides[get_db] = db_override
        router._password_limit._events.clear()
        token = create_access_token(self.user.id)
        with TestClient(app) as client, patch.object(service, "process_ticket"):
            unauthorized = client.get("/api/user/account-deletion/eligibility")
            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(unauthorized.headers["cache-control"], "no-store")
            self.assertEqual(unauthorized.headers["referrer-policy"], "no-referrer")
            invalid_password = client.post("/api/user/account-deletion/verify", json={"password": "secret-value-" * 20}, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(invalid_password.status_code, 422)
            self.assertNotIn("secret-value", invalid_password.text)
            self.assertEqual(invalid_password.headers["cache-control"], "no-store")
            invalid_ticket = client.post("/api/user/account-deletion/status", json={"ticket": "private-invalid-ticket"})
            self.assertEqual(invalid_ticket.status_code, 422)
            self.assertNotIn("private-invalid-ticket", invalid_ticket.text)
            self.assertEqual(invalid_ticket.headers["cache-control"], "no-store")
            verified = client.post("/api/user/account-deletion/verify", json={"password": self.password}, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(verified.status_code, 200)
            self.assertEqual(verified.headers["cache-control"], "no-store")
            ticket = verified.json()["data"]["ticket"]
            self.assertEqual(client.post("/api/user/account-deletion/submit", json={"ticket": ticket, "confirm": "true"}).status_code, 422)
            accepted = client.post("/api/user/account-deletion/submit", json={"ticket": ticket, "confirm": True})
            self.assertEqual(accepted.json()["data"]["status"], "processing")
            status = client.post("/api/user/account-deletion/status", json={"ticket": ticket})
            self.assertEqual(status.json()["data"]["status"], "processing")


if __name__ == "__main__":
    unittest.main()
