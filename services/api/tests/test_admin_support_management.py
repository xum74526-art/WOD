import unittest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.models import (
    FinanceAuditLog,
    Notification,
    SupportConversation,
    SupportMessage,
    SupportTicket,
    User,
)
from app.routers import admin as admin_router
from app.services.auth_session import create_authenticated_session
from app.utils.response import BizError, error


class AdminSupportManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.original_secret = settings.SECRET_KEY
        settings.SECRET_KEY = "admin-support-management-test-secret"

        self.admin = User(
            phone="13900007101", username="客服管理员", password="!", role="admin"
        )
        self.member = User(
            phone="13900007102", username="工单用户", password="!"
        )
        self.db.add_all([self.admin, self.member])
        self.db.flush()
        conversation = SupportConversation(user_id=self.member.id, language="zh")
        self.db.add(conversation)
        self.db.flush()
        question = SupportMessage(
            conversation_id=conversation.id,
            user_id=self.member.id,
            role="user",
            content="订单交付后无法连接",
            response_mode="user",
            client_message_id="support-user-question-0001",
        )
        self.db.add(question)
        self.db.flush()
        self.ticket = SupportTicket(
            ticket_no="KAI-TEST-0001",
            user_id=self.member.id,
            conversation_id=conversation.id,
            source_message_id=question.id,
            subject="连接异常",
            description="SSH 一直无法连接",
            category="order",
        )
        self.db.add(self.ticket)
        self.db.commit()

        session = create_authenticated_session(
            self.db,
            self.admin,
            platform="admin",
            client_id="admin",
            auth_method="test",
        )
        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        app.include_router(admin_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {session.token}"}

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        settings.SECRET_KEY = self.original_secret

    def action(self, action: str, expected_status: str, request_id: str, **extra):
        payload = {
            "action": action,
            "expected_status": expected_status,
            "request_id": request_id,
        }
        payload.update(extra)
        return self.client.post(
            f"/api/admin/support-tickets/{self.ticket.id}/actions",
            headers=self.headers,
            json=payload,
        )

    def test_operator_can_claim_reply_resolve_and_audit_ticket(self):
        queue = self.client.get(
            "/api/admin/support-tickets?status=pending_unassigned",
            headers=self.headers,
        )
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual(queue.json()["data"]["total"], 1)

        claimed = self.action("claim", "pending_unassigned", "support-claim-0001")
        self.assertEqual(claimed.status_code, 200, claimed.text)
        self.assertEqual(claimed.json()["data"]["ticket"]["status"], "assigned")
        self.assertEqual(claimed.json()["data"]["ticket"]["assigned_to"], self.admin.username)

        replied = self.action(
            "reply",
            "assigned",
            "support-reply-0001",
            reply="已收到，我们正在重新核验连接信息。",
        )
        self.assertEqual(replied.status_code, 200, replied.text)
        messages = replied.json()["data"]["messages"]["items"]
        self.assertEqual(messages[-1]["response_mode"], "human")
        self.assertEqual(messages[-1]["content"], "已收到，我们正在重新核验连接信息。")
        self.assertEqual(self.db.query(Notification).count(), 1)

        replay = self.action(
            "reply",
            "assigned",
            "support-reply-0001",
            reply="已收到，我们正在重新核验连接信息。",
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["data"]["idempotent_replay"])
        self.assertEqual(
            self.db.query(SupportMessage).filter(SupportMessage.response_mode == "human").count(),
            1,
        )

        resolved = self.action("resolve", "assigned", "support-resolve-0001")
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["data"]["ticket"]["status"], "resolved")
        self.assertEqual(self.db.query(FinanceAuditLog).count(), 3)

    def test_stale_status_is_rejected(self):
        response = self.action("resolve", "assigned", "support-stale-0001")
        self.assertEqual(response.status_code, 409, response.text)


if __name__ == "__main__":
    unittest.main()
