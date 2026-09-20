from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportConversation(Base):
    """A durable support thread owned by exactly one ZTW account."""

    __tablename__ = "support_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    language: Mapped[str] = mapped_column(String(8), default="zh")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class SupportMessage(Base):
    """A user or service reply persisted independently from the App process."""

    __tablename__ = "support_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "client_message_id", name="uq_support_message_user_client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("support_conversations.id"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system
    content: Mapped[str] = mapped_column(Text)
    response_mode: Mapped[str] = mapped_column(String(24), default="user")
    topic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    can_create_ticket: Mapped[bool] = mapped_column(Boolean, default=False)
    # App retries reuse this opaque identifier so a network timeout does not
    # create duplicate questions or duplicate assistant replies.
    client_message_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("support_messages.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SupportTicket(Base):
    """A real, queryable support ticket; assignment is never implied."""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("support_conversations.id"),
        index=True,
    )
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("support_messages.id"),
        nullable=True,
    )
    subject: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    # Until an operator system is configured, new tickets truthfully remain
    # pending_unassigned.  No fake agent, email address, or SLA is generated.
    status: Mapped[str] = mapped_column(String(32), default="pending_unassigned", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
