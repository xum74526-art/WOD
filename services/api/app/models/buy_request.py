from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BuyRequest(Base):
    __tablename__ = "buy_requests"
    __table_args__ = (
        Index(
            "uq_buy_requests_user_client_request",
            "user_id",
            "client_request_id",
            unique=True,
            sqlite_where=text("client_request_id IS NOT NULL"),
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_type: Mapped[str] = mapped_column(String(16), index=True)  # online/offline
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    gpu_variant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    gpu_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    billing_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="published", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    legacy_offline_purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("offline_purchases.id"), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BuyRequestQuote(Base):
    __tablename__ = "buy_request_quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    buy_request_id: Mapped[int] = mapped_column(ForeignKey("buy_requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    available_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BuyRequestQuoteRevision(Base):
    """Immutable negotiation history for one supplier quote.

    ``BuyRequestQuote`` remains the current-value projection used by installed
    clients.  Every initial offer and counteroffer is preserved here so a
    selected agreement always points to the exact terms both parties saw.
    """

    __tablename__ = "buy_request_quote_revisions"
    __table_args__ = (
        UniqueConstraint("quote_id", "revision_number", name="uq_buy_request_quote_revision"),
        Index("ix_buy_request_revision_request", "buy_request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("buy_request_quotes.id"), index=True)
    buy_request_id: Mapped[int] = mapped_column(ForeignKey("buy_requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    proposer_role: Mapped[str] = mapped_column(String(16))  # supplier / buyer
    proposer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("buy_request_quote_revisions.id"), nullable=True
    )
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    available_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BuyRequestDeal(Base):
    """Non-financial agreement and delivery lifecycle for a matched request."""

    __tablename__ = "buy_request_deals"
    __table_args__ = (
        # Active rows carry ``request:<id>`` and terminal rows clear it.  A
        # unique nullable slot gives SQLite and PostgreSQL the same one-active-
        # deal invariant while retaining rejected/declined history.
        Index("ux_buy_request_deals_active_slot", "active_slot", unique=True),
        Index("ix_buy_request_deals_request_created", "buy_request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    buy_request_id: Mapped[int] = mapped_column(ForeignKey("buy_requests.id"), index=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("buy_request_quotes.id"), index=True)
    selected_revision_id: Mapped[int] = mapped_column(
        ForeignKey("buy_request_quote_revisions.id"), index=True
    )
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="buyer_selected", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active_slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    supplier_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    platform_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    credential_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    credential_released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BuyRequestCredential(Base):
    """Encrypted SSH escrow payload; plaintext is never stored in this table."""

    __tablename__ = "buy_request_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("buy_request_deals.id"), unique=True, index=True
    )
    protected_payload: Mapped[str] = mapped_column(Text)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    envelope_namespace: Mapped[str] = mapped_column(String(64))
    envelope_version: Mapped[int] = mapped_column(Integer, default=1)
    credential_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="submitted", index=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    inspected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BuyRequestEvent(Base):
    """Sanitized audit timeline.  Credential material is never accepted here."""

    __tablename__ = "buy_request_events"
    __table_args__ = (
        Index("ix_buy_request_events_request_created", "buy_request_id", "created_at"),
        Index("ix_buy_request_events_deal_created", "deal_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    buy_request_id: Mapped[int] = mapped_column(ForeignKey("buy_requests.id"), index=True)
    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("buy_request_deals.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
