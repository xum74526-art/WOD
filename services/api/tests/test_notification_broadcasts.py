import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.rate_limit import notification_broadcast_rate_limit
from app.db.base import Base
from app.db.session import get_db
from app.models import Notification, NotificationBroadcast, NotificationPreference, User
from app.routers import admin as admin_router
from app.routers import notification as notification_router
from app.services.auth_session import create_authenticated_session
from app.utils.response import BizError, error


class NotificationBroadcastTests(unittest.TestCase):
    def setUp(self):
        notification_broadcast_rate_limit._events.clear()
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.original_secret = settings.SECRET_KEY
        settings.SECRET_KEY = "notification-broadcast-test-secret"

        self.admin = User(phone="13900001001", username="公告管理员", password="!", role="admin")
        self.active_a = User(phone="13900001002", username="有效用户 A", password="!", account_status="active")
        self.active_b = User(phone="13900001003", username="有效用户 B", password="!", account_status="active")
        self.suspended = User(phone="13900001004", username="停用用户", password="!", account_status="suspended")
        self.deleting = User(phone="13900001005", username="注销中用户", password="!", account_status="deleting")
        self.db.add_all([self.admin, self.active_a, self.active_b, self.suspended, self.deleting])
        self.db.commit()
        for row in (self.admin, self.active_a, self.active_b, self.suspended, self.deleting):
            self.db.refresh(row)
        # A platform announcement is safety/operations information.  It must
        # still reach an active account that opted out of optional system
        # notices, otherwise it would not be a true all-user message.
        self.db.add(NotificationPreference(user_id=self.active_a.id, system_enabled=False))
        self.db.commit()

        issued = create_authenticated_session(
            self.db,
            self.admin,
            platform="admin",
            client_id="admin",
            auth_method="test",
        )
        personal_issued = create_authenticated_session(
            self.db,
            self.active_a,
            platform="web",
            client_id="web",
            auth_method="test",
        )

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        app.include_router(admin_router.router)
        app.include_router(notification_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {issued.token}"}
        self.user_headers = {"Authorization": f"Bearer {personal_issued.token}"}

    def tearDown(self):
        self.client.close()
        self.db.close()
        settings.SECRET_KEY = self.original_secret

    def _payload(self, **overrides):
        payload = {
            "client_request_id": "broadcast-test-001",
            "title": "平台服务公告",
            "content": "今晚 23:00 进行例行维护。",
            "title_en": "Platform maintenance",
            "content_en": "Routine maintenance starts at 23:00.",
            "notification_type": "system",
            "action_url": "/pages/notifications/index",
        }
        payload.update(overrides)
        return payload

    def test_admin_broadcast_reaches_only_active_accounts_and_is_audited(self):
        response = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(),
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["recipient_count"], 3)  # admin + two active users
        self.assertEqual(data["status"], "completed")
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 1)
        rows = self.db.query(Notification).filter(Notification.dedupe_key == f"broadcast:{data['id']}").all()
        self.assertEqual({row.user_id for row in rows}, {self.admin.id, self.active_a.id, self.active_b.id})
        self.assertFalse(self.db.query(Notification).filter(Notification.user_id == self.suspended.id).count())
        self.assertFalse(self.db.query(Notification).filter(Notification.user_id == self.deleting.id).count())

    def test_retry_is_idempotent_and_payload_reuse_is_rejected(self):
        first = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(),
            headers=self.admin_headers,
        )
        second = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(),
            headers=self.admin_headers,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 1)
        self.assertEqual(self.db.query(Notification).filter(Notification.dedupe_key.like("broadcast:%")).count(), 3)

        changed = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(content="换一条正文"),
            headers=self.admin_headers,
        )
        self.assertEqual(changed.status_code, 409, changed.text)

    def test_non_admin_cannot_publish(self):
        response = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(client_request_id="broadcast-test-002"),
            headers=self.user_headers,
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 0)

    def test_unsafe_action_path_is_rejected_before_any_audience_is_written(self):
        response = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-test-unsafe",
                action_url="/pages/%2e%2e/profile/index",
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 0)
        self.assertEqual(self.db.query(Notification).count(), 0)

    def test_history_is_paginated(self):
        response = self.client.get(
            "/api/admin/notification-broadcasts?page=1&page_size=20",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])

    def test_latest_major_announcement_is_public_and_ignores_newer_regular_messages(self):
        empty = self.client.get("/api/notifications/major-announcement")
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertIsNone(empty.json()["data"])

        major = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-major-001",
                title="重要服务公告",
                content="平台将在今晚升级服务。",
                notification_type="major_announcement",
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(major.status_code, 200, major.text)

        regular = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-system-002",
                title="普通系统消息",
                content="这条消息只进入通知中心。",
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(regular.status_code, 200, regular.text)

        response = self.client.get("/api/notifications/major-announcement")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["id"], major.json()["data"]["id"])
        self.assertEqual(data["title"], "重要服务公告")
        self.assertNotIn("actor_user_id", data)
        self.assertNotIn("recipient_count", data)

        inbox_rows = self.db.query(Notification).filter(
            Notification.dedupe_key == f"broadcast:{data['id']}"
        ).all()
        self.assertEqual({row.type for row in inbox_rows}, {"major_announcement"})

        replacement = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-major-003",
                title="新的重要公告",
                content="新的重大公告应替换首页展示。",
                notification_type="major_announcement",
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(replacement.status_code, 200, replacement.text)
        latest = self.client.get("/api/notifications/major-announcement").json()["data"]
        self.assertEqual(latest["id"], replacement.json()["data"]["id"])
        self.assertEqual(latest["title"], "新的重要公告")

    def test_expired_announcement_leaves_audit_but_disappears_from_public_and_inbox(self):
        expiry = datetime.now(timezone.utc) + timedelta(days=1)
        created = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-expiry-001",
                title="限时公告",
                content="过期后不再展示。",
                notification_type="major_announcement",
                expires_at=expiry.isoformat(),
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        broadcast_id = created.json()["data"]["id"]
        self.assertIsNotNone(created.json()["data"]["expires_at"])

        expired_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        broadcast = self.db.get(NotificationBroadcast, broadcast_id)
        broadcast.expires_at = expired_at
        self.db.query(Notification).filter(
            Notification.dedupe_key == f"broadcast:{broadcast_id}",
        ).update({"expires_at": expired_at}, synchronize_session=False)
        self.db.commit()

        public = self.client.get("/api/notifications/major-announcement")
        self.assertIsNone(public.json()["data"])
        inbox = self.client.get("/api/notifications", headers=self.user_headers).json()["data"]
        self.assertNotIn("限时公告", {item["title"] for item in inbox["items"]})
        self.assertEqual(inbox["unread"], 1)  # only the one-time inbox welcome remains
        history = self.client.get(
            "/api/admin/notification-broadcasts",
            headers=self.admin_headers,
        ).json()["data"]
        self.assertEqual(history["items"][0]["status"], "expired")
        self.assertEqual(self.db.get(NotificationBroadcast, broadcast_id).status, "completed")

    def test_admin_can_revoke_without_erasing_audit_and_regular_user_cannot(self):
        created = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-revoke-001",
                title="待撤销公告",
                content="该公告将被管理员撤销。",
                notification_type="major_announcement",
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(created.status_code, 200, created.text)
        broadcast_id = created.json()["data"]["id"]

        denied = self.client.post(
            f"/api/admin/notification-broadcasts/{broadcast_id}/revoke",
            json={"reason": "普通用户不能撤销"},
            headers=self.user_headers,
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        revoked = self.client.post(
            f"/api/admin/notification-broadcasts/{broadcast_id}/revoke",
            json={"reason": "维护计划已经取消"},
            headers=self.admin_headers,
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        data = revoked.json()["data"]
        self.assertEqual(data["status"], "revoked")
        self.assertEqual(data["revoked_by_user_id"], self.admin.id)
        self.assertEqual(data["revoke_reason"], "维护计划已经取消")
        self.assertIsNotNone(data["revoked_at"])
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 1)
        recipient_rows = self.db.query(Notification).filter(
            Notification.dedupe_key == f"broadcast:{broadcast_id}",
        ).all()
        self.assertEqual(len(recipient_rows), 3)
        self.assertTrue(all(row.deleted_at is not None and row.is_read for row in recipient_rows))
        self.assertIsNone(self.client.get("/api/notifications/major-announcement").json()["data"])

        repeated = self.client.post(
            f"/api/admin/notification-broadcasts/{broadcast_id}/revoke",
            json={"reason": "重复请求不会覆盖首次审计"},
            headers=self.admin_headers,
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["data"]["revoke_reason"], "维护计划已经取消")

    def test_past_expiration_is_rejected_before_delivery(self):
        response = self.client.post(
            "/api/admin/notification-broadcasts",
            json=self._payload(
                client_request_id="broadcast-expiry-past",
                expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            ),
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.query(NotificationBroadcast).count(), 0)


if __name__ == "__main__":
    unittest.main()
