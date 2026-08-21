import unittest
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import SupportConversation, SupportMessage, SupportTicket, User  # noqa: F401
from app.routers.chat import chat, create_support_ticket, get_support_session
from app.schemas.support import SupportMessageIn, SupportTicketIn
from app.services.support import match_faq
from app.utils.response import BizError


class SupportChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(username="客服测试", phone="13900000801", password="!")
        self.other_user = User(username="其他用户", phone="13900000802", password="!")
        self.db.add_all([self.user, self.other_user])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)

    def tearDown(self):
        self.db.close()

    async def test_builtin_faq_persists_and_retry_is_idempotent_without_ai_key(self):
        request = SupportMessageIn(
            message="哪些算力可以购买，订单如何交付？",
            client_message_id="support-test-message-001",
            lang="zh",
        )
        with patch.object(settings, "AI_PROVIDER", ""), patch.object(settings, "AI_API_KEY", ""), patch.object(settings, "DEEPSEEK_API_KEY", ""):
            first = await chat(request, self.user, self.db)
            second = await chat(request, self.user, self.db)

        self.assertEqual(first["data"]["service_mode"], "self_service")
        self.assertIn("测试订单", first["data"]["reply"])
        self.assertFalse(first["data"]["can_create_ticket"])
        self.assertEqual(first["data"]["message"]["id"], second["data"]["message"]["id"])
        self.assertEqual(self.db.query(SupportConversation).filter_by(user_id=self.user.id).count(), 1)
        self.assertEqual(self.db.query(SupportMessage).filter_by(user_id=self.user.id).count(), 2)

        session = get_support_session("zh", self.user, self.db)["data"]
        self.assertEqual(session["conversation_id"], first["data"]["conversation_id"])
        self.assertEqual(len(session["messages"]), 2)
        self.assertFalse(session["human_support_configured"])

    async def test_unknown_question_can_create_real_unassigned_ticket(self):
        with patch.object(settings, "AI_PROVIDER", ""), patch.object(settings, "AI_API_KEY", ""), patch.object(settings, "DEEPSEEK_API_KEY", ""):
            answer = await chat(SupportMessageIn(
                message="我有一个无法归类的特殊问题 ZZZ",
                client_message_id="support-test-message-002",
                lang="zh",
            ), self.user, self.db)
        self.assertTrue(answer["data"]["can_create_ticket"])
        self.assertIn("待分配", answer["data"]["reply"])

        created = create_support_ticket(SupportTicketIn(
            conversation_id=answer["data"]["conversation_id"],
            source_message_id=answer["data"]["message"]["id"],
            subject="特殊问题",
            description="需要人工后续核查的特殊问题",
            category="other",
            lang="zh",
        ), self.user, self.db)["data"]
        ticket = created["ticket"]
        self.assertRegex(ticket["ticket_no"], r"^WOD-\d{8}-[A-F0-9]{6}$")
        self.assertEqual(ticket["status"], "pending_unassigned")
        self.assertIsNone(ticket["assigned_to"])
        self.assertEqual(self.db.query(SupportTicket).filter_by(user_id=self.user.id).count(), 1)

    async def test_conversation_and_ticket_are_scoped_to_authenticated_owner(self):
        answer = await chat(SupportMessageIn(
            message="登录失败怎么办？",
            client_message_id="support-test-message-003",
            lang="zh",
        ), self.user, self.db)
        with self.assertRaises(BizError) as caught:
            create_support_ticket(SupportTicketIn(
                conversation_id=answer["data"]["conversation_id"],
                subject="越权工单",
                description="不应创建",
                lang="zh",
            ), self.other_user, self.db)
        self.assertEqual(caught.exception.status_code, 404)

    def test_inputs_are_bounded_and_faq_is_bilingual(self):
        with self.assertRaises(ValidationError):
            SupportMessageIn(message="x" * 1001, lang="zh")
        with self.assertRaises(ValidationError):
            SupportTicketIn(conversation_id=1, subject=" ", description="test")
        self.assertEqual(match_faq("How can I withdraw to my bank card?", "en").topic, "withdrawal")
        self.assertEqual(match_faq("设备托管怎么审核", "zh").topic, "hosting")


if __name__ == "__main__":
    unittest.main()
