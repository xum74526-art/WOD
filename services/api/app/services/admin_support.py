from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.support import SupportConversation, SupportMessage, SupportTicket
from app.models.user import User
from app.schemas.support import AdminSupportTicketActionIn
from app.services.manual_payout import record_audit
from app.services.notification_service import create_notification
from app.utils.response import BizError


SUPPORT_TICKET_STATUSES = ("pending_unassigned", "assigned", "resolved", "closed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ticket_out(ticket: SupportTicket, owner: User | None = None) -> dict:
    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "user": {
            "id": ticket.user_id,
            "username": owner.username if owner else None,
        },
        "conversation_id": ticket.conversation_id,
        "source_message_id": ticket.source_message_id,
        "subject": ticket.subject,
        "description": ticket.description,
        "category": ticket.category,
        "status": ticket.status,
        "assigned_to": ticket.assigned_to,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def list_admin_support_tickets(
    db: Session,
    *,
    status: str | None,
    category: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict:
    query = db.query(SupportTicket, User).join(User, User.id == SupportTicket.user_id)
    if status:
        query = query.filter(SupportTicket.status == status)
    if category:
        query = query.filter(SupportTicket.category == category)
    normalized = str(keyword or "").strip()
    if normalized:
        query = query.filter(or_(
            SupportTicket.ticket_no.contains(normalized),
            SupportTicket.subject.contains(normalized),
            User.username.contains(normalized),
        ))
    total = query.count()
    rows = query.order_by(
        SupportTicket.updated_at.desc(), SupportTicket.id.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_ticket_out(ticket, owner) for ticket, owner in rows],
    }


def get_admin_support_ticket(
    db: Session,
    *,
    ticket_id: int,
    message_page: int,
    message_page_size: int,
) -> dict:
    row = db.query(SupportTicket, User).join(
        User, User.id == SupportTicket.user_id
    ).filter(SupportTicket.id == ticket_id).first()
    if row is None:
        raise BizError("客服工单不存在", status_code=404)
    ticket, owner = row
    message_query = db.query(SupportMessage).filter(
        SupportMessage.conversation_id == ticket.conversation_id,
        SupportMessage.user_id == ticket.user_id,
    )
    message_total = message_query.count()
    messages = message_query.order_by(
        SupportMessage.id.asc()
    ).offset((message_page - 1) * message_page_size).limit(message_page_size).all()
    return {
        "ticket": _ticket_out(ticket, owner),
        "messages": {
            "total": message_total,
            "page": message_page,
            "page_size": message_page_size,
            "items": [{
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "response_mode": item.response_mode,
                "topic": item.topic,
                "reply_to_id": item.reply_to_id,
                "created_at": item.created_at,
            } for item in messages],
        },
    }


def _notify_ticket_owner(
    db: Session,
    *,
    ticket: SupportTicket,
    action: str,
    reply: str | None,
    request_id: str,
) -> None:
    copy = {
        "reply": (
            "客服工单有新回复",
            reply or "客服人员已回复您的工单。",
            "New support ticket reply",
            reply or "A support operator replied to your ticket.",
        ),
        "resolve": (
            "客服工单已解决",
            "您的客服工单已标记为已解决，如仍需协助可在客服页面继续反馈。",
            "Support ticket resolved",
            "Your support ticket was marked resolved. Reopen it from Support if you still need help.",
        ),
        "close": (
            "客服工单已关闭",
            "您的客服工单已关闭，如有新问题可重新提交工单。",
            "Support ticket closed",
            "Your support ticket was closed. You can create a new ticket for another issue.",
        ),
        "reopen": (
            "客服工单已重新处理",
            "您的客服工单已重新打开，客服人员将继续处理。",
            "Support ticket reopened",
            "Your support ticket was reopened and an operator will continue handling it.",
        ),
    }.get(action)
    if copy is None:
        return
    create_notification(
        db,
        user_id=ticket.user_id,
        title=copy[0],
        content=copy[1],
        title_en=copy[2],
        content_en=copy[3],
        notification_type="system",
        action_url="/pages/kefu/index",
        dedupe_key=f"support-ticket:{ticket.id}:{action}:{request_id}",
        respect_preferences=False,
    )


def perform_admin_support_action(
    db: Session,
    *,
    ticket_id: int,
    actor: User,
    data: AdminSupportTicketActionIn,
) -> dict:
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id
    ).with_for_update().first()
    if ticket is None:
        raise BizError("客服工单不存在", status_code=404)
    if data.action == "reply":
        existing_reply = db.query(SupportMessage).filter(
            SupportMessage.user_id == ticket.user_id,
            SupportMessage.client_message_id == f"admin:{data.request_id}",
        ).first()
        if existing_reply is not None:
            if existing_reply.conversation_id != ticket.conversation_id:
                raise BizError("该请求标识已用于另一条客服回复", status_code=409)
            return get_admin_support_ticket(
                db,
                ticket_id=ticket.id,
                message_page=1,
                message_page_size=100,
            ) | {"idempotent_replay": True}
    if ticket.status != data.expected_status:
        raise BizError("工单状态已更新，请刷新后重试", status_code=409)

    action = data.action
    previous_status = ticket.status
    if action == "claim":
        if ticket.status != "pending_unassigned":
            raise BizError("只有待分配工单可以认领", status_code=409)
        ticket.assigned_to = actor.username
        ticket.status = "assigned"
    elif action == "assign":
        if ticket.status not in {"pending_unassigned", "assigned"}:
            raise BizError("当前工单不能重新分配", status_code=409)
        if data.assignee_user_id is None:
            raise BizError("请选择接收工单的管理员")
        assignee = db.query(User).filter(
            User.id == data.assignee_user_id,
            User.role == "admin",
            User.account_status == "active",
        ).first()
        if assignee is None:
            raise BizError("接收管理员不存在或不可用", status_code=404)
        ticket.assigned_to = assignee.username
        ticket.status = "assigned"
    elif action == "reply":
        if not data.reply:
            raise BizError("请输入回复内容")
        if ticket.status == "pending_unassigned":
            ticket.assigned_to = actor.username
            ticket.status = "assigned"
        elif ticket.status != "assigned":
            raise BizError("已结束的工单不能直接回复，请先重新打开", status_code=409)
        elif ticket.assigned_to != actor.username:
            raise BizError("请先将工单分配给当前管理员", status_code=409)
        client_message_id = f"admin:{data.request_id}"
        db.add(SupportMessage(
            conversation_id=ticket.conversation_id,
            user_id=ticket.user_id,
            role="assistant",
            content=data.reply,
            response_mode="human",
            topic="human_support",
            can_create_ticket=False,
            client_message_id=client_message_id,
        ))
    elif action in {"resolve", "close"}:
        allowed = {"assigned"} if action == "resolve" else {"assigned", "resolved"}
        if ticket.status not in allowed:
            raise BizError("当前工单不能执行该操作", status_code=409)
        if ticket.assigned_to != actor.username:
            raise BizError("请先将工单分配给当前管理员", status_code=409)
        ticket.status = "resolved" if action == "resolve" else "closed"
    elif action == "reopen":
        if ticket.status not in {"resolved", "closed"}:
            raise BizError("只有已解决或已关闭工单可以重新打开", status_code=409)
        ticket.status = "assigned"
        ticket.assigned_to = actor.username
    else:
        raise BizError("不支持的工单操作")

    ticket.updated_at = _utcnow()
    conversation = db.query(SupportConversation).filter(
        SupportConversation.id == ticket.conversation_id
    ).first()
    if conversation:
        # A conversation can contain multiple tickets. Closing one ticket must
        # never hide its reply history or prevent the user from continuing the
        # same support thread.
        conversation.status = "open"
        conversation.updated_at = ticket.updated_at
    _notify_ticket_owner(
        db,
        ticket=ticket,
        action=action,
        reply=data.reply,
        request_id=data.request_id,
    )
    record_audit(
        db,
        actor_user_id=actor.id,
        action=f"support_ticket_{action}",
        object_type="support_ticket",
        object_id=ticket.id,
        detail={
            "request_id": data.request_id,
            "previous_status": previous_status,
            "status": ticket.status,
            "assigned_to": ticket.assigned_to,
            "note": data.note,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if action == "reply":
            existing_reply = db.query(SupportMessage).filter(
                SupportMessage.user_id == ticket.user_id,
                SupportMessage.client_message_id == f"admin:{data.request_id}",
            ).first()
            if existing_reply is not None:
                return get_admin_support_ticket(
                    db,
                    ticket_id=ticket.id,
                    message_page=1,
                    message_page_size=100,
                ) | {"idempotent_replay": True}
        raise
    return get_admin_support_ticket(
        db,
        ticket_id=ticket.id,
        message_page=1,
        message_page_size=100,
    )
