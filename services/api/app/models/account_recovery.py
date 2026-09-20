from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountRecoveryToken(Base):
    """Short-lived, single-use proof for narrowly scoped identity flows.

    Only a SHA-256 digest of the opaque token is persisted.  Email values are
    populated only for recovery-email purposes and are encrypted with the same
    field-level protection used by other sensitive account data; fingerprints
    are keyed and used only for equality lookup.
    """

    __tablename__ = "account_recovery_tokens"
    __table_args__ = (
        Index("ix_account_recovery_tokens_user_id", "user_id"),
        Index("ix_account_recovery_tokens_purpose", "purpose"),
        Index("ix_account_recovery_tokens_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    target_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_email_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auth_version_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
