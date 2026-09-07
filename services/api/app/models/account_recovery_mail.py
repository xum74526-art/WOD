"""Durable delivery queue for account-recovery mail."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountRecoveryMailOutbox(Base):
    """An at-least-once SMTP job whose sensitive payload is encrypted at rest.

    ``recipient_payload`` and ``token_payload`` contain values protected by the
    field-level Fernet key.  They are cleared as soon as a job reaches a
    terminal state.  Public requests for addresses that are not attached to an
    account create a short-lived ``suppressed`` row so their response and
    durable-write semantics do not disclose account membership.
    """

    __tablename__ = "account_recovery_mail_outbox"
    __table_args__ = (
        Index("ix_account_recovery_mail_outbox_user_id", "user_id"),
        Index(
            "ux_account_recovery_mail_outbox_recovery_token_id",
            "recovery_token_id",
            unique=True,
        ),
        Index(
            "ix_account_recovery_mail_outbox_status_available",
            "status",
            "available_at",
        ),
        Index("ix_account_recovery_mail_outbox_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    recovery_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_recovery_tokens.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
