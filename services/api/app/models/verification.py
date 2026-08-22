from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    real_name: Mapped[str] = mapped_column(String(64))
    id_card: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/verified/rejected
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    front_photo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    back_photo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # OCR is only a local document-data pre-check.  ``status`` remains pending
    # until an operator explicitly approves the application.
    ocr_status: Mapped[str] = mapped_column(String(24), default="not_started")
    ocr_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Random generation token for the current identity/photo input set.  OCR
    # workers may write a result only while this token still matches.
    ocr_input_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
