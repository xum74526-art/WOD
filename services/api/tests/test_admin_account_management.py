import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.sensitive import fingerprint, protect
from app.db.base import Base
from app.db.session import get_db
from app.models import (
    AccountAdminAction,
    AccountDeletionRequest,
    AccountRecoveryMailOutbox,
    AccountRecoveryToken,
    AuthSession,
    User,
    Wallet,
)
from app.routers import admin as admin_router
from app.services.auth_session import create_authenticated_session
from app.utils.response import BizError, error


class AdminAccountManagementTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.original_secret = settings.SECRET_KEY
        self.original_sensitive_key = settings.SENSITIVE_DATA_KEY
        settings.SECRET_KEY = "admin-account-management-test-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")

        email = "member@example.com"
        self.admin = User(
            phone="13900002001", username="平台管理员", password="!", role="admin"
        )
        self.user = User(
            phone="13900002002",
            username="普通用户",
            password="!",
            recovery_email=protect(email),
            recovery_email_fingerprint=fingerprint(email),
            recovery_email_verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.other_admin = User(
            phone="13900002003", username="其他管理员", password="!", role="admin"
        )
        self.deletable = User(
            phone="13900002004", username="待注销用户", password="!"
        )
        self.no_email = User(
            phone="13900002005", username="无邮箱用户", password="!"
        )
        self.db.add_all([
            self.admin,
            self.user,
            self.other_admin,
            self.deletable,
            self.no_email,
        ])
        self.db.commit()
        for row in (self.admin, self.user, self.other_admin, self.deletable, self.no_email):
            self.db.refresh(row)

        admin_session = create_authenticated_session(
            self.db,
            self.admin,
            platform="admin",
            client_id="admin",
            auth_method="test",
        )
        user_session = create_authenticated_session(
            self.db,
            self.user,
            platform="web",
            client_id="web",
            auth_method="test",
        )
        self.user_session_id = user_session.session.id

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(request: Request, exc: BizError):
            return JSONResponse(
                status_code=exc.status_code,
                content=error(exc.msg, exc.code),
            )

        app.include_router(admin_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {admin_session.token}"}
        self.user_headers = {"Authorization": f"Bearer {user_session.token}"}

    def tearDown(self):
        self.client.close()
        self.db.close()
        settings.SECRET_KEY = self.original_secret
        settings.SENSITIVE_DATA_KEY = self.original_sensitive_key

    @staticmethod
    def payload(action: str, request_id: str, **extra):
        value = {
            "action": action,
            "client_request_id": request_id,
            "reason": "客服已完成身份与问题核验",
        }
        value.update(extra)
        return value

    def post_action(self, user_id: int, payload: dict):
        return self.client.post(
            f"/api/admin/users/{user_id}/actions",
            json=payload,
            headers=self.admin_headers,
        )

    def test_user_list_exposes_management_state_without_private_email(self):
        response = self.client.get("/api/admin/users", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        item = next(
            row for row in response.json()["data"]["items"]
            if row["id"] == self.user.id
        )
        self.assertEqual(item["account_status"], "active")
        self.assertTrue(item["recovery_email_verified"])
        self.assertIn("password_set", item)
        self.assertNotIn("recovery_email", item)

    def test_admin_can_queue_reset_email_without_receiving_token_or_address(self):
        with patch("app.services.account_recovery.require_email_delivery"):
            response = self.post_action(
                self.user.id,
                self.payload("send_password_reset", "admin-reset-0001"),
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["result_code"], "reset_email_queued")
        self.assertNotIn("token", data)
        self.assertNotIn("email", data)
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 1)
        self.assertEqual(self.db.query(AccountRecoveryMailOutbox).count(), 1)
        self.assertEqual(self.db.query(AccountAdminAction).count(), 1)

        with patch("app.services.account_recovery.require_email_delivery"):
            repeated = self.post_action(
                self.user.id,
                self.payload("send_password_reset", "admin-reset-0001"),
            )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["data"]["id"], data["id"])
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 1)
        self.assertEqual(self.db.query(AccountAdminAction).count(), 1)

    def test_reset_requires_a_verified_recovery_channel(self):
        with patch("app.services.account_recovery.require_email_delivery"):
            response = self.post_action(
                self.no_email.id,
                self.payload("send_password_reset", "admin-reset-0002"),
            )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("未绑定已验证", response.json()["msg"])
        self.assertEqual(self.db.query(AccountAdminAction).count(), 0)

    def test_freeze_revokes_every_session_and_unfreeze_does_not_restore_it(self):
        frozen = self.post_action(
            self.user.id,
            self.payload("freeze", "admin-freeze-0001"),
        )
        self.assertEqual(frozen.status_code, 200, frozen.text)
        self.db.refresh(self.user)
        session = self.db.get(AuthSession, self.user_session_id)
        self.assertEqual(self.user.account_status, "suspended")
        self.assertEqual(self.user.auth_version, 1)
        self.assertIsNotNone(session.revoked_at)
        history = self.client.get(
            f"/api/admin/users/{self.user.id}/actions?page=1&page_size=20",
            headers=self.admin_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        history_data = history.json()["data"]
        self.assertEqual(history_data["total"], 1)
        self.assertEqual(history_data["items"][0]["actor_user_id"], self.admin.id)
        self.assertEqual(history_data["items"][0]["reason"], "客服已完成身份与问题核验")
        denied = self.client.get("/api/admin/users", headers=self.user_headers)
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertIn("冻结", denied.json()["msg"])

        unfrozen = self.post_action(
            self.user.id,
            self.payload("unfreeze", "admin-unfreeze-0001"),
        )
        self.assertEqual(unfrozen.status_code, 200, unfrozen.text)
        self.db.refresh(self.user)
        self.assertEqual(self.user.account_status, "active")
        self.assertEqual(self.user.auth_version, 2)
        still_denied = self.client.get("/api/admin/users", headers=self.user_headers)
        self.assertEqual(still_denied.status_code, 401, still_denied.text)

    def test_delete_requires_name_confirmation_and_has_financial_blockers(self):
        mismatch = self.post_action(
            self.deletable.id,
            self.payload(
                "delete",
                "admin-delete-0001",
                confirm_username="错误用户名",
            ),
        )
        self.assertEqual(mismatch.status_code, 400, mismatch.text)

        self.db.add(Wallet(user_id=self.deletable.id, balance=1, frozen=0))
        self.db.commit()
        blocked = self.post_action(
            self.deletable.id,
            self.payload(
                "delete",
                "admin-delete-0002",
                confirm_username=self.deletable.username,
            ),
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn("余额", blocked.json()["msg"])
        self.db.refresh(self.deletable)
        self.assertEqual(self.deletable.account_status, "active")

        wallet = self.db.query(Wallet).filter(Wallet.user_id == self.deletable.id).one()
        wallet.balance = 0
        self.db.commit()
        accepted = self.post_action(
            self.deletable.id,
            self.payload(
                "delete",
                "admin-delete-0003",
                confirm_username=self.deletable.username,
            ),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.db.refresh(self.deletable)
        self.assertEqual(self.deletable.account_status, "deleting")
        self.assertEqual(accepted.json()["data"]["result_code"], "deletion_queued")
        self.assertEqual(
            self.db.query(AccountDeletionRequest).filter_by(
                user_id=self.deletable.id,
                status="processing",
            ).count(),
            1,
        )

    def test_admin_cannot_manage_self_or_another_admin(self):
        self_action = self.post_action(
            self.admin.id,
            self.payload("freeze", "admin-protected-0001"),
        )
        peer_action = self.post_action(
            self.other_admin.id,
            self.payload("freeze", "admin-protected-0002"),
        )
        self.assertEqual(self_action.status_code, 403, self_action.text)
        self.assertEqual(peer_action.status_code, 403, peer_action.text)

    def test_non_admin_cannot_manage_accounts(self):
        response = self.client.post(
            f"/api/admin/users/{self.no_email.id}/actions",
            json=self.payload("freeze", "admin-denied-0001"),
            headers=self.user_headers,
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_audit_reason_rejects_long_sensitive_numbers(self):
        response = self.post_action(
            self.no_email.id,
            self.payload(
                "freeze",
                "admin-sensitive-0001",
                reason="用户提交银行卡 6222020202020202020",
            ),
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.db.refresh(self.no_email)
        self.assertEqual(self.no_email.account_status, "active")
        self.assertEqual(self.db.query(AccountAdminAction).count(), 0)


if __name__ == "__main__":
    unittest.main()
