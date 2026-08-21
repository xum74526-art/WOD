from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# ``active`` and ``pending_review`` are historical states from the first
# closed-test workflow.  Neither state represented verification by a bank.
# Keep them eligible during the transition, but expose them as ``registered``
# and never as bank-verified.
REGISTERED_CARD_STATUSES = ("registered", "pending_review", "active")


def public_bank_card_status(status: str | None) -> str:
    return "registered" if not status or status in REGISTERED_CARD_STATUSES else status


class BankCard(Base):
    __tablename__ = "bank_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "card_fingerprint", name="uq_bank_card_user_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(64))
    card_number: Mapped[str] = mapped_column(Text)
    holder: Mapped[str] = mapped_column(String(64))
    # Encrypted at rest; Fernet ciphertext is intentionally larger than the
    # original 11-digit phone number.
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    card_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="registered", index=True)
    verification_mode: Mapped[str] = mapped_column(String(24), default="format_only")
    review_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
