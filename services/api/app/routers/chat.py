"""Durable bilingual self-service support with optional AI and real tickets."""

from __future__ import annotations

from datetime import datetime
from secrets import token_hex

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import limit_support_message, limit_support_ticket
from app.db.session import get_db
from app.models.support import SupportConversation, SupportMessage, SupportTicket
from app.models.user import User
from app.schemas.support import SupportMessageIn, SupportMessageOut, SupportTicketIn, SupportTicketOut
from app.services.support import asks_for_human, human_request_reply, localized_builtin_reply, match_faq, unknown_reply
from app.services.trade_mode import direct_trade_enabled, matchmaking_enabled
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/chat", tags=["support"])

DIRECT_TRADE_SYSTEM_FACTS = """- A current KAI Pricing quote explicitly marked Purchasable can create an hourly
  order, reserve wallet CH, and wait for manual platform SSH delivery.
- KAI Pricing is the sole active live quote source. Quote observations are not
  live inventory, and listings marked reference-only cannot be ordered."""

MATCHMAKING_SYSTEM_FACTS = """- This release is a matchmaking service: users submit requirements, verified
  sellers quote, and choosing a quote records only a cooperation intention for
  platform coordination. It does not create a paid order, debit CH, or collect money.
- KAI Pricing observations and charts remain visible for inquiry reference; they
  are not live inventory or a transaction price. KAI-operated and seller resources
  are identified separately.
- Buyer contact details, seller contact details, and SSH credentials must not be
  disclosed during the quote stage."""

HISTORY_ONLY_SYSTEM_FACTS = """- Requirement matching and direct transactions are currently unavailable.
- Market observations, charts, and historical account records remain readable."""


def _system_prompt() -> str:
    if direct_trade_enabled():
        commerce_facts = DIRECT_TRADE_SYSTEM_FACTS
    elif matchmaking_enabled():
        commerce_facts = MATCHMAKING_SYSTEM_FACTS
    else:
        commerce_facts = HISTORY_ONLY_SYSTEM_FACTS
    return f"""You are the KAI compute-platform support assistant.
Only answer from these verified product facts:
{commerce_facts}
- Payment, recharge, refund, withdrawal, SMS verification, push delivery, and
  human-agent systems are available only when the server explicitly enables them.
- Never claim a payment, payout, human handoff, email, phone, SLA, or feature is
  available unless the supplied context explicitly says so.
- Never request passwords, full identity numbers, bank card numbers, or SSH secrets.
- Keep the answer concise and tell the user they can create a stored support ticket
  when the question cannot be answered reliably.
"""


def _ai_configuration() -> tuple[str, str, str, str] | None:
    """Return an OpenAI-compatible adapter config without exposing credentials."""

    provider = settings.AI_PROVIDER.strip().lower()
    api_key = settings.AI_API_KEY.strip()
    base_url = settings.AI_BASE_URL.strip()
    model = settings.AI_MODEL.strip()
    if not provider and settings.DEEPSEEK_API_KEY.strip():
        provider = "openai_compatible"
        api_key = settings.DEEPSEEK_API_KEY.strip()
        base_url = settings.DEEPSEEK_BASE_URL.strip()
        model = settings.DEEPSEEK_MODEL.strip()
    if provider not in {"openai_compatible", "deepseek"}:
        return None
    if not api_key or not base_url or not model:
        return None
    return provider, api_key, base_url.rstrip("/"), model


def _service_mode() -> str:
    return "ai_assisted" if _ai_configuration() else "self_service"


def _conversation_for_user(
    db: Session,
    user_id: int,
    conversation_id: int | None,
    lang: str,
) -> SupportConversation:
    if conversation_id:
        conversation = db.query(SupportConversation).filter(
            SupportConversation.id == conversation_id,
            SupportConversation.user_id == user_id,
        ).first()
        if not conversation:
            raise BizError("客服会话不存在", status_code=404)
        if conversation.status != "open":
            raise BizError("客服会话已关闭", status_code=409)
        conversation.language = lang
        return conversation
    conversation = db.query(SupportConversation).filter(
        SupportConversation.user_id == user_id,
        SupportConversation.status == "open",
    ).order_by(SupportConversation.updated_at.desc(), SupportConversation.id.desc()).first()
    if conversation:
        conversation.language = lang
        return conversation
    conversation = SupportConversation(user_id=user_id, language=lang, status="open")
    db.add(conversation)
    db.flush()
    return conversation


def _message_dict(message: SupportMessage, lang: str | None = None) -> dict:
    content = message.content
    if lang in {"zh", "en"} and message.role == "assistant" and message.response_mode == "self_service":
        content = localized_builtin_reply(message.topic, lang) or content
    return SupportMessageOut(
        id=message.id,
        role=message.role,
        content=content,
        response_mode=message.response_mode,
        topic=message.topic,
        can_create_ticket=message.can_create_ticket,
        reply_to_id=message.reply_to_id,
        created_at=message.created_at,
    ).model_dump()


def _ticket_dict(ticket: SupportTicket) -> dict:
    return SupportTicketOut(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        conversation_id=ticket.conversation_id,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        status=ticket.status,
        assigned_to=ticket.assigned_to,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    ).model_dump()


async def _optional_ai_reply(message: str, lang: str, recent_messages: list[SupportMessage]) -> str | None:
    config = _ai_configuration()
    if not config:
        return None
    _, api_key, base_url, model = config
    language_instruction = (
        "Reply entirely in concise English. Use CH for the platform unit."
        if lang == "en"
        else "请始终使用简洁、专业的中文回答，平台单位写作“卡时”。"
    )
    messages = [{"role": "system", "content": f"{_system_prompt()}\n{language_instruction}"}]
    for item in recent_messages[-10:]:
        if item.role in {"user", "assistant"}:
            messages.append({"role": item.role, "content": item.content[:1000]})
    messages.append({"role": "user", "content": message})
    try:
        async with httpx.AsyncClient(timeout=settings.AI_HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 500,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if isinstance(content, str) and content.strip():
                return content.strip()[:4000]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        # The built-in service remains usable when an optional provider fails.
        return None
    return None


@router.get("/session")
def get_support_session(
    lang: str = Query(default="zh", pattern="^(zh|en)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(SupportConversation).filter(
        SupportConversation.user_id == user.id,
        SupportConversation.status == "open",
    ).order_by(SupportConversation.updated_at.desc(), SupportConversation.id.desc()).first()
    messages: list[SupportMessage] = []
    if conversation:
        messages = db.query(SupportMessage).filter(
            SupportMessage.conversation_id == conversation.id,
            SupportMessage.user_id == user.id,
        ).order_by(SupportMessage.id.asc()).limit(100).all()
    tickets = db.query(SupportTicket).filter(SupportTicket.user_id == user.id).order_by(
        SupportTicket.created_at.desc(), SupportTicket.id.desc()
    ).limit(20).all()
    return success({
        "conversation_id": conversation.id if conversation else None,
        "service_mode": _service_mode(),
        "human_support_configured": False,
        "messages": [_message_dict(item, lang) for item in messages],
        "tickets": [_ticket_dict(item) for item in tickets],
        "notice": (
            "Self-service FAQ is available. Human agents are not configured."
            if lang == "en" else
            "自助客服已启用，人工坐席尚未配置。"
        ),
    })


@router.post("")
async def chat(
    data: SupportMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_support_message(user.id)
    conversation = _conversation_for_user(db, user.id, data.conversation_id, data.lang)

    # A retry after an App/network timeout returns the already persisted reply.
    if data.client_message_id:
        existing = db.query(SupportMessage).filter(
            SupportMessage.user_id == user.id,
            SupportMessage.client_message_id == data.client_message_id,
        ).first()
        if existing:
            if existing.conversation_id != conversation.id:
                raise BizError("客户端消息标识已被使用", status_code=409)
            reply = db.query(SupportMessage).filter(
                SupportMessage.conversation_id == conversation.id,
                SupportMessage.reply_to_id == existing.id,
                SupportMessage.role == "assistant",
            ).order_by(SupportMessage.id.desc()).first()
            if reply:
                return success({
                    "conversation_id": conversation.id,
                    "message": _message_dict(reply),
                    "reply": reply.content,
                    "is_human": False,
                    "service_mode": _service_mode(),
                    "can_create_ticket": reply.can_create_ticket,
                })
            user_message = existing
        else:
            user_message = SupportMessage(
                conversation_id=conversation.id,
                user_id=user.id,
                role="user",
                content=data.message,
                response_mode="user",
                client_message_id=data.client_message_id,
            )
            db.add(user_message)
            db.flush()
    else:
        user_message = SupportMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=data.message,
            response_mode="user",
        )
        db.add(user_message)
        db.flush()

    faq = match_faq(data.message, data.lang)
    can_create_ticket = False
    if asks_for_human(data.message, data.lang):
        reply_text = human_request_reply(data.lang)
        response_mode = "self_service"
        topic = "human_support"
        can_create_ticket = True
    elif faq:
        reply_text = faq.en if data.lang == "en" else faq.zh
        response_mode = "self_service"
        topic = faq.topic
    else:
        recent = db.query(SupportMessage).filter(
            SupportMessage.conversation_id == conversation.id,
        ).order_by(SupportMessage.id.desc()).limit(10).all()
        ai_reply = await _optional_ai_reply(data.message, data.lang, list(reversed(recent)))
        if ai_reply:
            reply_text = ai_reply
            response_mode = "ai_assisted"
            topic = "ai"
        else:
            reply_text = unknown_reply(data.lang)
            response_mode = "self_service"
            topic = "other"
            can_create_ticket = True

    reply = SupportMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=reply_text,
        response_mode=response_mode,
        topic=topic,
        can_create_ticket=can_create_ticket,
        reply_to_id=user_message.id,
    )
    conversation.updated_at = datetime.now()
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return success({
        "conversation_id": conversation.id,
        "message": _message_dict(reply),
        "reply": reply.content,
        "is_human": False,
        "service_mode": _service_mode(),
        "can_create_ticket": reply.can_create_ticket,
    })


def _new_ticket_no(db: Session) -> str:
    day = datetime.now().strftime("%Y%m%d")
    for _ in range(10):
        value = f"WOD-{day}-{token_hex(3).upper()}"
        if not db.query(SupportTicket.id).filter(SupportTicket.ticket_no == value).first():
            return value
    raise BizError("工单编号生成失败，请重试", status_code=503)


@router.post("/tickets")
def create_support_ticket(
    data: SupportTicketIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_support_ticket(user.id)
    conversation = db.query(SupportConversation).filter(
        SupportConversation.id == data.conversation_id,
        SupportConversation.user_id == user.id,
    ).first()
    if not conversation:
        raise BizError("客服会话不存在", status_code=404)
    if data.source_message_id:
        source = db.query(SupportMessage).filter(
            SupportMessage.id == data.source_message_id,
            SupportMessage.conversation_id == conversation.id,
            SupportMessage.user_id == user.id,
        ).first()
        if not source:
            raise BizError("客服消息不存在", status_code=404)

    ticket = SupportTicket(
        ticket_no=_new_ticket_no(db),
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=data.source_message_id,
        subject=data.subject,
        description=data.description,
        category=data.category,
        status="pending_unassigned",
        assigned_to=None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return success({
        "ticket": _ticket_dict(ticket),
        "notice": (
            "Ticket saved as Pending assignment. Human agents and a response SLA are not configured yet."
            if data.lang == "en" else
            "工单已保存为“待分配”。目前尚未配置人工坐席和回复时限。"
        ),
    })


@router.get("/tickets")
def list_support_tickets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tickets = db.query(SupportTicket).filter(SupportTicket.user_id == user.id).order_by(
        SupportTicket.created_at.desc(), SupportTicket.id.desc()
    ).limit(50).all()
    return success({"items": [_ticket_dict(ticket) for ticket in tickets]})
