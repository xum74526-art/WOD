"""Add Mazfu payment metadata and webhook audit events.

Revision ID: 0016_mazfu_payments
Revises: 0015_cross_platform_agent
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016_mazfu_payments"
down_revision: str | Sequence[str] | None = "0015_cross_platform_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("payment_intents") as batch_op:
        batch_op.add_column(
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}")
        )
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column(
            "payment_intent_id",
            BIGINT,
            sa.ForeignKey("payment_intents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_key", name="uq_payment_webhook_provider_event"),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'rejected', 'failed')",
            name="ck_payment_webhook_events_status",
        ),
    )
    op.create_index(
        "ix_payment_webhook_intent_created",
        "payment_webhook_events",
        ["payment_intent_id", "created_at"],
    )
    op.create_index(
        "ix_payment_webhook_status_created",
        "payment_webhook_events",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_webhook_status_created", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_intent_created", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
    with op.batch_alter_table("payment_intents") as batch_op:
        batch_op.drop_column("metadata")
