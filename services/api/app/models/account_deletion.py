from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountDeletionRequest(Base):
    """Deletion-only capability and durable cleanup outbox; never a login token."""

    __tablename__ = "account_deletion_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="verified", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    receipt_expires_at: Mapped[datetime] = mapped_column(DateTime)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_scrubbed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleanup_paths: Mapped[list] = mapped_column(JSON, default=list)
    last_error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
