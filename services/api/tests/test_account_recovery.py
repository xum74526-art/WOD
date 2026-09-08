"""Account-recovery tests use only synthetic users and in-memory SQLite."""

from __future__ import annotations

import hashlib
import smtplib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import rate_limit as rate_limits
from app.core.config import settings
from app.core.deps import get_current_auth_context
from app.core.security import hash_password, verify_password
from app.core.sensitive import fingerprint, protect, reveal
from app.db.base import Base
from app.db.session import get_db
from app.integrations import account_email
from app.models import (
    AccountRecoveryMailOutbox,
    AccountRecoveryToken,
    AuthSession,
    ExternalAuthFlow,
    ExternalIdentity,
    User,
)
from app.routers import account_recovery as recovery_router
from app.routers import user as user_router
from app.services import account_recovery as recovery
from app.services import kai_auth
from app.services.auth_session import create_authenticated_session, utcnow
from app.utils.email_address import normalize_email
from app.utils.response import BizError


_RECOVERY_LIMITERS = (
    rate_limits.recovery_request_global_rate_limit,
    rate_limits.recovery_request_account_rate_limit,
    rate_limits.recovery_confirm_global_rate_limit,
    rate_limits.recovery_confirm_token_rate_limit,
    rate_limits.recovery_binding_rate_limit,
)


class AccountRecoveryTests(unittest.TestCase):
    password = "Synthetic-Password-42"

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
        self.original_settings = {
            name: getattr(settings, name)
            for name in (
                "SECRET_KEY",
                "SENSITIVE_DATA_KEY",
                "ACCOUNT_RECOVERY_EMAIL_ENABLED",
                "ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN",
                "ACCOUNT_RECOVERY_VERIFY_TTL_SECONDS",
                "ACCOUNT_RECOVERY_RESET_TTL_SECONDS",
                "ACCOUNT_RECOVERY_KAI_TTL_SECONDS",
                "ACCOUNT_RECOVERY_SMTP_HOST",
                "ACCOUNT_RECOVERY_SMTP_PORT",
                "ACCOUNT_RECOVERY_SMTP_USERNAME",
                "ACCOUNT_RECOVERY_SMTP_PASSWORD",
                "ACCOUNT_RECOVERY_SMTP_FROM",
                "ACCOUNT_RECOVERY_SMTP_STARTTLS",
                "ACCOUNT_RECOVERY_SMTP_SSL",
                "KAI_AUTH_ISSUER",
                "KAI_AUTH_CLIENT_ID",
                "KAI_AUTH_CLIENT_SECRET",
                "KAI_AUTH_CALLBACK_URL",
                "KAI_AUTH_APP_RETURN_URL",
                "KAI_AUTH_ALLOWED_RETURN_URLS",
            )
        }
        settings.SECRET_KEY = "account-recovery-unit-test-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        settings.ACCOUNT_RECOVERY_EMAIL_ENABLED = True
        settings.ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN = "https://web.wod.test"
        settings.ACCOUNT_RECOVERY_VERIFY_TTL_SECONDS = 1800
        settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS = 1800
        settings.ACCOUNT_RECOVERY_KAI_TTL_SECONDS = 600
        settings.ACCOUNT_RECOVERY_SMTP_HOST = "smtp.wod.test"
        settings.ACCOUNT_RECOVERY_SMTP_PORT = 587
        settings.ACCOUNT_RECOVERY_SMTP_USERNAME = ""
        settings.ACCOUNT_RECOVERY_SMTP_PASSWORD = ""
        settings.ACCOUNT_RECOVERY_SMTP_FROM = "no-reply@wod.test"
        settings.ACCOUNT_RECOVERY_SMTP_STARTTLS = True
        settings.ACCOUNT_RECOVERY_SMTP_SSL = False
        settings.KAI_AUTH_ISSUER = "https://auth.kai.test"
        settings.KAI_AUTH_CLIENT_ID = "wod-recovery-test"
        settings.KAI_AUTH_CLIENT_SECRET = "synthetic-secret"
        settings.KAI_AUTH_CALLBACK_URL = "https://api.wod.test/api/auth/kai/callback"
        settings.KAI_AUTH_APP_RETURN_URL = "wod://auth/kai"
        settings.KAI_AUTH_ALLOWED_RETURN_URLS = "https://web.wod.test/reset-password"
        self._clear_rate_limits()

    def tearDown(self):
        self._clear_rate_limits()
        for name, value in self.original_settings.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _clear_rate_limits():
        for limiter in _RECOVERY_LIMITERS:
            with limiter._lock:
                limiter._events.clear()

    def _user(self, suffix: int = 1, *, status: str = "active") -> User:
        user = User(
            phone=f"1390000{suffix:04d}",
            username=f"Synthetic recovery user {suffix}",
            password=hash_password(self.password),
            account_status=status,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _request_verification(self, user: User, email: str) -> str:
        already_verified, token, recipient = recovery.request_email_verification(
            self.db,
            user,
            email,
            self.password,
        )
        self.assertFalse(already_verified)
        self.assertIsNotNone(token)
        self.assertEqual(recipient, normalize_email(email))
        return str(token)

    def test_email_normalization_is_stable_and_rejects_invalid_addresses(self):
        self.assertEqual(
            normalize_email("  Alice.Example@EXAMPLE.COM.  "),
            "alice.example@example.com",
        )
        self.assertEqual(
            normalize_email("Owner@例子.测试"),
            "owner@xn--fsqu00a.xn--0zwm56d",
        )
        for invalid in ("", "missing-at.example.com", ".owner@example.com", "a@localhost"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_email(invalid)

    def test_binding_email_copy_uses_linked_email_terminology(self):
        with patch.object(account_email, "_deliver") as deliver:
            account_email.send_account_recovery_email(
                "verify_email",
                "owner@example.com",
                "synthetic-binding-token",
            )

        message = deliver.call_args.args[0]
        self.assertEqual(message["Subject"], "验证你的 WOD 绑定邮箱")
        content = message.get_content()
        self.assertIn("为 WOD 账号绑定或更换邮箱", content)
        self.assertIn("完成邮箱绑定", content)
        self.assertNotIn("找回邮箱", f"{message['Subject']}\n{content}")

        with patch.object(settings, "ACCOUNT_RECOVERY_EMAIL_ENABLED", False):
            with self.assertRaisesRegex(BizError, "邮箱服务尚未配置"):
                account_email.require_email_delivery()

    def test_password_reset_email_supports_native_code_and_web_fallback(self):
        with patch.object(account_email, "_deliver") as deliver:
            account_email.send_account_recovery_email(
                "password_reset_email",
                "owner@example.com",
                "synthetic-reset-token",
            )

        message = deliver.call_args.args[0]
        content = message.get_content()
        self.assertEqual(message["Subject"], "重置你的 WOD 密码")
        self.assertIn("在 WOD App", content)
        self.assertIn(
            "页面输入以下重置码：\nsynthetic-reset-token\n\n",
            content,
        )
        self.assertIn(
            account_email._link("password_reset_email", "synthetic-reset-token"),
            content,
        )

    def test_email_binding_requires_password_and_persists_only_protected_proof(self):
        user = self._user()
        with self.assertRaisesRegex(BizError, "当前密码错误"):
            recovery.request_email_verification(
                self.db,
                user,
                "Owner@Example.COM",
                "incorrect-password",
            )
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

        token = self._request_verification(user, "Owner@Example.COM")
        row = self.db.query(AccountRecoveryToken).one()
        normalized = "owner@example.com"
        self.assertEqual(row.token_hash, hashlib.sha256(token.encode("utf-8")).hexdigest())
        self.assertNotEqual(row.token_hash, token)
        self.assertNotIn(token, repr(row.__dict__))
        self.assertTrue(row.target_email.startswith("enc:v1:"))
        self.assertNotIn(normalized, row.target_email)
        self.assertEqual(reveal(row.target_email), normalized)
        self.assertEqual(row.target_email_fingerprint, fingerprint(normalized))
        self.assertIsNone(user.recovery_email)
        self.assertIsNone(user.recovery_email_verified_at)

    def test_email_binding_rechecks_password_and_auth_version_after_account_lock(self):
        user = self._user()

        def concurrent_password_change(db, user_id):
            db.query(User).filter(User.id == user_id).update(
                {User.password: hash_password("Concurrent-Password-73")},
                synchronize_session=False,
            )

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_password_change):
            with self.assertRaisesRegex(BizError, "当前密码错误"):
                recovery.request_email_verification(
                    self.db,
                    user,
                    "owner@example.com",
                    self.password,
                )
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

        def concurrent_auth_rotation(db, user_id):
            db.query(User).filter(User.id == user_id).update(
                {User.auth_version: User.auth_version + 1},
                synchronize_session=False,
            )

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_auth_rotation):
            with self.assertRaisesRegex(BizError, "会话无效或已过期"):
                recovery.request_email_verification(
                    self.db,
                    user,
                    "owner@example.com",
                    self.password,
                )
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

    def test_email_binding_does_not_disclose_another_accounts_address(self):
        owner = self._user(1)
        contender = self._user(2)
        normalized = "shared@example.com"
        owner.recovery_email = protect(normalized)
        owner.recovery_email_fingerprint = fingerprint(normalized)
        owner.recovery_email_verified_at = utcnow()
        self.db.commit()

        already_verified, token, recipient = recovery.request_email_verification(
            self.db,
            contender,
            normalized,
            self.password,
        )

        self.assertFalse(already_verified)
        self.assertIsNone(token)
        self.assertEqual(recipient, normalized)
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

    def test_email_verification_is_single_use_and_expired_tokens_do_not_bind(self):
        user = self._user()
        token = self._request_verification(user, "verified@example.com")
        recovery.confirm_recovery_email(self.db, token)
        self.db.refresh(user)
        self.assertEqual(reveal(user.recovery_email), "verified@example.com")
        self.assertIsNotNone(user.recovery_email_verified_at)
        row = self.db.query(AccountRecoveryToken).filter_by(
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest()
        ).one()
        self.assertIsNotNone(row.consumed_at)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            recovery.confirm_recovery_email(self.db, token)

        expiring_user = self._user(2)
        expired_token = self._request_verification(expiring_user, "expired@example.com")
        expired_row = self.db.query(AccountRecoveryToken).filter_by(
            token_hash=hashlib.sha256(expired_token.encode("utf-8")).hexdigest()
        ).one()
        expired_row.expires_at = utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            recovery.confirm_recovery_email(self.db, expired_token)
        self.db.refresh(expiring_user)
        self.assertIsNone(expiring_user.recovery_email)
        self.assertIsNone(expiring_user.recovery_email_verified_at)

    def test_replacing_recovery_email_invalidates_old_mailbox_reset_proof(self):
        user = self._user()
        recovery.confirm_recovery_email(
            self.db,
            self._request_verification(user, "old-owner@example.com"),
        )
        issued = recovery.request_password_reset(self.db, "old-owner@example.com")
        self.assertIsNotNone(issued)
        old_reset_token, _recipient = issued

        recovery.confirm_recovery_email(
            self.db,
            self._request_verification(user, "new-owner@example.com"),
        )

        old_reset_row = self.db.query(AccountRecoveryToken).filter_by(
            token_hash=hashlib.sha256(old_reset_token.encode("utf-8")).hexdigest()
        ).one()
        self.assertIsNotNone(old_reset_row.consumed_at)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            recovery.reset_password(
                self.db,
                old_reset_token,
                "Replacement-Password-73",
            )

    def test_public_reset_rechecks_mailbox_and_version_after_account_lock(self):
        user = self._user()
        old_email = "old-owner@example.com"
        user.recovery_email = protect(old_email)
        user.recovery_email_fingerprint = fingerprint(old_email)
        user.recovery_email_verified_at = utcnow()
        self.db.commit()

        def concurrent_email_change(db, user_id):
            db.query(User).filter(User.id == user_id).update(
                {
                    User.recovery_email: protect("new-owner@example.com"),
                    User.recovery_email_fingerprint: fingerprint("new-owner@example.com"),
                    User.recovery_email_verified_at: utcnow(),
                },
                synchronize_session=False,
            )

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_email_change):
            self.assertIsNone(recovery.request_password_reset(self.db, old_email))
        self.assertEqual(
            self.db.query(AccountRecoveryToken).filter_by(
                purpose=recovery.PASSWORD_RESET_EMAIL
            ).count(),
            0,
        )

        def concurrent_auth_rotation(db, user_id):
            db.query(User).filter(User.id == user_id).update(
                {User.auth_version: User.auth_version + 1},
                synchronize_session=False,
            )

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_auth_rotation):
            self.assertIsNone(recovery.request_password_reset(self.db, old_email))
        self.assertEqual(
            self.db.query(AccountRecoveryToken).filter_by(
                purpose=recovery.PASSWORD_RESET_EMAIL
            ).count(),
            0,
        )

    def test_public_reset_request_is_indistinguishable_and_never_uses_network(self):
        user = self._user()
        normalized = "known@example.com"
        user.recovery_email = protect(normalized)
        user.recovery_email_fingerprint = fingerprint(normalized)
        user.recovery_email_verified_at = utcnow()
        self.db.commit()

        app = FastAPI()
        app.include_router(recovery_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        with (
            patch.object(account_email, "send_account_recovery_email") as sender,
            patch.object(
                smtplib,
                "SMTP",
                side_effect=AssertionError("unit tests must not open SMTP sockets"),
            ) as smtp,
            patch.object(
                smtplib,
                "SMTP_SSL",
                side_effect=AssertionError("unit tests must not open SMTP sockets"),
            ) as smtp_ssl,
            TestClient(app) as client,
        ):
            known = client.post(
                "/api/auth/email/password-reset/request",
                json={"email": " Known@Example.COM "},
            )
            unknown = client.post(
                "/api/auth/email/password-reset/request",
                json={"email": "unknown@example.com"},
            )

        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.content, unknown.content)
        self.assertEqual(known.headers["cache-control"], "no-store")
        self.assertEqual(unknown.headers["cache-control"], "no-store")
        self.assertFalse(any(
            "known@example.com" in key or "unknown@example.com" in key
            for key in rate_limits.recovery_request_account_rate_limit._events
        ))
        sender.assert_not_called()
        outbox = self.db.query(AccountRecoveryMailOutbox).order_by(
            AccountRecoveryMailOutbox.id
        ).all()
        self.assertEqual([row.status for row in outbox], ["pending", "suppressed"])
        self.assertTrue(outbox[0].recipient_payload.startswith("enc:v1:"))
        self.assertNotIn(normalized, repr(outbox[0].__dict__))
        self.assertEqual(reveal(outbox[0].recipient_payload), normalized)
        self.assertIsNone(outbox[1].recipient_payload)
        self.assertIsNone(outbox[1].token_payload)
        raw_token = reveal(outbox[0].token_payload)
        self.assertTrue(raw_token)
        self.assertIsNotNone(outbox[0].recovery_token_id)
        self.assertIsNone(outbox[1].recovery_token_id)
        row = self.db.query(AccountRecoveryToken).filter_by(
            purpose=recovery.PASSWORD_RESET_EMAIL
        ).one()
        self.assertEqual(outbox[0].recovery_token_id, row.id)
        self.assertEqual(
            row.token_hash,
            hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        )
        smtp.assert_not_called()
        smtp_ssl.assert_not_called()

    def test_reset_refuses_an_internally_mismatched_email_proof(self):
        user = self._user()
        user.recovery_email = protect("different@example.com")
        user.recovery_email_fingerprint = fingerprint("requested@example.com")
        user.recovery_email_verified_at = utcnow()
        self.db.commit()

        self.assertIsNone(
            recovery.request_password_reset(self.db, "requested@example.com")
        )
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

    def test_password_changed_notice_contains_no_recovery_secret_or_link(self):
        with patch.object(account_email, "_deliver") as deliver:
            account_email.send_password_changed_notice("notice@example.com")

        message = deliver.call_args.args[0]
        self.assertEqual(message["To"], "notice@example.com")
        self.assertIn("密码已更新", message["Subject"])
        content = message.get_content()
        self.assertNotIn("http://", content)
        self.assertNotIn("https://", content)
        self.assertNotIn("token", content.casefold())

    def test_password_reset_is_single_use_rotates_auth_and_revokes_every_session(self):
        user = self._user()
        user.recovery_email = protect("notice@example.com")
        user.recovery_email_fingerprint = fingerprint("notice@example.com")
        user.recovery_email_verified_at = utcnow()
        self.db.commit()
        legacy_token = jwt.encode(
            {
                "sub": str(user.id),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        self.assertEqual(get_current_auth_context(token=legacy_token, db=self.db).user.id, user.id)
        issued_tokens = []
        for platform in ("web", "ios", "android"):
            issued = create_authenticated_session(
                self.db,
                user,
                platform=platform,
                client_id=platform,
                auth_method="password",
            )
            issued_tokens.append(issued.token)

        reset_token = recovery.issue_kai_recovery_token(self.db, user)
        notification_recipient = recovery.reset_password(
            self.db,
            reset_token,
            "Replacement-Password-73",
        )
        self.assertEqual(notification_recipient, "notice@example.com")
        self.db.refresh(user)
        self.assertEqual(user.auth_version, 1)
        self.assertFalse(verify_password(self.password, user.password))
        self.assertTrue(verify_password("Replacement-Password-73", user.password))
        self.assertEqual(
            self.db.query(AuthSession).filter_by(user_id=user.id).count(),
            3,
        )
        self.assertEqual(
            self.db.query(AuthSession).filter_by(user_id=user.id, revoked_at=None).count(),
            0,
        )
        for old_token in (legacy_token, *issued_tokens):
            with self.subTest(token=old_token[:12]), self.assertRaises(HTTPException) as raised:
                get_current_auth_context(token=old_token, db=self.db)
            self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            recovery.reset_password(self.db, reset_token, "Another-Password-84")

    def test_authenticated_password_change_keeps_current_session_only(self):
        user = self._user()
        current = create_authenticated_session(
            self.db,
            user,
            platform="web",
            client_id="web",
            auth_method="password",
        )
        other = create_authenticated_session(
            self.db,
            user,
            platform="android",
            client_id="android",
            auth_method="password",
        )
        stale_recovery_token = recovery.issue_kai_recovery_token(self.db, user)

        app = FastAPI()
        app.include_router(user_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        with TestClient(app) as client:
            response = client.post(
                "/api/user/password",
                headers={"Authorization": f"Bearer {current.token}"},
                json={
                    "old_password": self.password,
                    "new_password": "Replacement-Password-73",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["revoked_other_sessions"], 1)
        self.db.refresh(current.session)
        self.db.refresh(other.session)
        self.assertIsNone(current.session.revoked_at)
        self.assertIsNotNone(other.session.revoked_at)
        self.assertEqual(
            get_current_auth_context(token=current.token, db=self.db).user.id,
            user.id,
        )
        with self.assertRaises(HTTPException):
            get_current_auth_context(token=other.token, db=self.db)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            recovery.reset_password(
                self.db,
                stale_recovery_token,
                "Another-Password-84",
            )

    def test_authenticated_password_change_rechecks_session_and_password_after_lock(self):
        user = self._user()
        current = create_authenticated_session(
            self.db,
            user,
            platform="web",
            client_id="web",
            auth_method="password",
        )

        def concurrent_session_revoke(db, user_id):
            db.query(AuthSession).filter(
                AuthSession.id == current.session.id,
                AuthSession.user_id == user_id,
            ).update({AuthSession.revoked_at: utcnow()}, synchronize_session=False)

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_session_revoke):
            with self.assertRaisesRegex(BizError, "会话无效或已过期"):
                recovery.change_password_and_revoke_other_sessions(
                    self.db,
                    user,
                    self.password,
                    "Replacement-Password-73",
                    current.session.id,
                )
        self.db.refresh(user)
        self.assertTrue(verify_password(self.password, user.password))

        def concurrent_password_change(db, user_id):
            db.query(User).filter(User.id == user_id).update(
                {User.password: hash_password("Concurrent-Password-73")},
                synchronize_session=False,
            )

        with patch.object(recovery, "lock_active_user", side_effect=concurrent_password_change):
            with self.assertRaisesRegex(BizError, "原密码错误"):
                recovery.change_password_and_revoke_other_sessions(
                    self.db,
                    user,
                    self.password,
                    "Replacement-Password-84",
                    current.session.id,
                )

    def test_deleted_or_deleting_account_cannot_use_a_preissued_reset_token(self):
        for suffix, status in ((1, "deleting"), (2, "deleted")):
            with self.subTest(status=status):
                user = self._user(suffix)
                token = recovery.issue_kai_recovery_token(self.db, user)
                original_hash = user.password
                user.account_status = status
                self.db.commit()
                with self.assertRaisesRegex(BizError, "已注销或正在注销"):
                    recovery.reset_password(self.db, token, "Replacement-Password-73")
                self.db.rollback()
                self.db.refresh(user)
                self.assertEqual(user.password, original_hash)
                self.assertEqual(user.auth_version, 0)
                row = self.db.query(AccountRecoveryToken).filter_by(
                    token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest()
                ).one()
                self.assertIsNone(row.consumed_at)

    def test_kai_recovery_is_fresh_and_resolves_only_bound_issuer_subject(self):
        authorization_url = kai_auth.create_authorization_flow(
            self.db,
            "recover",
            "https://web.wod.test/reset-password",
            platform="web",
            client_id="web",
        )
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(query["prompt"], ["login"])
        flow = self.db.query(ExternalAuthFlow).one()
        self.assertEqual(flow.intent, "recover")
        self.assertIsNone(flow.user_id)

        bound_user = self._user(1)
        other_issuer_user = self._user(2)
        self.db.add_all(
            [
                ExternalIdentity(
                    user_id=bound_user.id,
                    provider="kai",
                    issuer=settings.KAI_AUTH_ISSUER,
                    subject="bound-subject",
                    email="same-profile-email@example.com",
                    email_verified=True,
                ),
                ExternalIdentity(
                    user_id=other_issuer_user.id,
                    provider="kai",
                    issuer="https://different-issuer.kai.test",
                    subject="other-issuer-subject",
                    email="other@example.com",
                    email_verified=True,
                ),
            ]
        )
        self.db.commit()

        # Matching a cached profile email is never sufficient.
        self.assertIsNone(
            kai_auth.find_bound_user(
                self.db,
                {"sub": "unbound-subject", "email": "same-profile-email@example.com"},
            )
        )
        # The same subject under a different issuer is also not a WOD binding.
        self.assertIsNone(
            kai_auth.find_bound_user(
                self.db,
                {"sub": "other-issuer-subject", "email": "other@example.com"},
            )
        )
        found = kai_auth.find_bound_user(
            self.db,
            {"sub": "bound-subject", "email": "changed-profile-email@example.com"},
        )
        self.assertEqual(found.id, bound_user.id)
        self.assertEqual(self.db.query(User).count(), 2)


if __name__ == "__main__":
    unittest.main()
