from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentOrder(Base):
    """One provider payment mapped to one wallet credit.

    Money is persisted directly in CNY. ``card_hours`` is a compatibility
    column whose value now equals ``amount_cny`` at the fixed 1:1 rate.
    ``credited_at`` is the idempotency
    boundary: a verified provider notification and wallet credit are committed
    in the same database transaction.
    """

    __tablename__ = "payment_orders"
    __table_args__ = (
        Index(
            "ux_payment_order_user_provider_request",
            "user_id",
            "provider",
            "client_request_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="mapay")
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_trade_no: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    # A validated provider URL makes reopening a checkout token idempotent.
    provider_checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Recorded before outbound create I/O so other workers can distinguish an
    # in-flight request from an abandoned/uncertain upstream order.
    checkout_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    card_hour_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    checkout_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconcile_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PaymentEvent(Base):
    """Sanitized, append-only evidence for one payment state transition."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_payment_event_dedupe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="system")
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(32), default="system")
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    # Only service-selected fields belong here.  Raw callbacks, signatures,
    # provider keys, card data and bearer checkout tokens are forbidden.
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentRefund(Base):
    """One full, original-rail CNY refund for a recharge payment.

    This is deliberately separate from the wallet/order ``refund`` ledger
    semantics. A provider refund may be uncertain while wallet balance
    remain frozen, so the saga has its own durable state.
    """

    __tablename__ = "payment_refunds"
    __table_args__ = (
        UniqueConstraint("payment_order_id", name="uq_payment_refund_order"),
        UniqueConstraint(
            "actor_user_id",
            "client_request_id",
            name="uq_payment_refund_actor_request",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    payment_order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id"), index=True
    )
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(24), default="submitting", index=True)
    wallet_hold_status: Mapped[str] = mapped_column(
        String(24), default="not_required"
    )
    previous_payment_status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(500))
    provider_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_message: Mapped[str | None] = mapped_column(String(160), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PaymentRefundRequest(Base):
    """A customer's request for an administrator-reviewed recharge refund.

    Creating this row never freezes wallet funds and never contacts the
    payment provider.  Those financial side effects remain behind the
    administrator refund workflow represented by :class:`PaymentRefund`.
    """

    __tablename__ = "payment_refund_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_request_id",
            name="uq_payment_refund_request_user_client",
        ),
        UniqueConstraint(
            "active_payment_order_id",
            name="uq_payment_refund_request_active_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    payment_order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id"), index=True
    )
    # Only active requests populate this column.  Clearing it on a terminal
    # rejection/cancellation later permits a new application while retaining
    # the full audit history.  The unique constraint prevents two concurrent
    # active requests for the same payment.
    active_payment_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_orders.id"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    card_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(
        String(24), default="pending_review", server_default="pending_review", index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_refund_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_refunds.id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
