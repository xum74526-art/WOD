from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WithdrawalOrder(Base):
    __tablename__ = "withdrawal_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "client_request_id", name="uq_withdraw_user_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    bank_card_id: Mapped[int] = mapped_column(ForeignKey("bank_cards.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="reviewing", index=True)

    amount_card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    locked_rate_cny: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    gross_amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fee_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    net_amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    # Immutable, non-secret display snapshots.  The complete account number is
    # retrieved from the still-encrypted BankCard only through the explicitly
    # audited payment-instructions endpoint.
    bank_name_snapshot: Mapped[str] = mapped_column(String(64))
    card_last4_snapshot: Mapped[str] = mapped_column(String(4))
    holder_snapshot: Mapped[str] = mapped_column(String(64))

    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The first non-approving administrator who reveals payment instructions
    # owns the external bank-transfer step for the lifetime of this request.
    # This durable binding prevents two finance operators from both paying the
    # same request before either one reaches the final database CAS.
    payout_actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    bank_reference: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    paid_amount_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PayoutReceipt(Base):
    __tablename__ = "payout_receipts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    withdrawal_id: Mapped[int] = mapped_column(
        ForeignKey("withdrawal_orders.id"), unique=True, index=True
    )
    storage_path: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentInstructionGrant(Base):
    """Short-lived proof that one finance operator revealed payout details.

    Only a SHA-256 digest of the opaque browser token is stored.  The grant is
    bound to the withdrawal version and a digest of the current bank-card
    fields, then consumed in the same transaction that marks the payout paid.
    """

    __tablename__ = "payment_instruction_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    withdrawal_id: Mapped[int] = mapped_column(
        ForeignKey("withdrawal_orders.id"), index=True
    )
    bank_card_id: Mapped[int] = mapped_column(ForeignKey("bank_cards.id"), index=True)
    order_version: Mapped[int] = mapped_column(Integer)
    card_snapshot_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinanceAuditLog(Base):
    __tablename__ = "finance_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
