"""Enforce dedicated server listings and add compensation refunds.

Revision ID: 0018_dedicated_server_refunds
Revises: 0017_agent_hardware_inventory
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_dedicated_server_refunds"
down_revision: str | Sequence[str] | None = "0017_agent_hardware_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.execute("UPDATE products SET available_quantity = 1, price_unit = 'server_hour'")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("ck_products_total_quantity", type_="check")
        batch_op.create_check_constraint("ck_products_single_server", "available_quantity = 1")
        batch_op.create_check_constraint("ck_products_price_unit", "price_unit = 'server_hour'")
        batch_op.alter_column("price_unit", server_default="server_hour")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("ck_orders_payment_status", type_="check")
        batch_op.create_check_constraint(
            "ck_orders_payment_status",
            "payment_status IN ('not_required', 'pending', 'paid', 'refund_pending', 'refunded')",
        )
    with op.batch_alter_table("payment_intents") as batch_op:
        batch_op.drop_constraint("ck_payment_intents_status", type_="check")
        batch_op.create_check_constraint(
            "ck_payment_intents_status",
            "status IN ('created', 'provider_pending', 'succeeded', 'failed', 'cancelled', 'expired', 'refund_pending', 'refunded')",
        )

    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.add_column(sa.Column("agent_service_checks", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("agent_service_observed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("agent_service_status", sa.String(16), nullable=False, server_default="pending"))
        batch_op.create_check_constraint(
            "ck_merchant_servers_agent_service_status",
            "agent_service_status IN ('pending', 'healthy', 'unhealthy', 'stale', 'unavailable')",
        )

    op.create_table(
        "refund_requests",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("refund_no", sa.String(32), nullable=False, unique=True),
        sa.Column("payment_intent_id", BIGINT, sa.ForeignKey("payment_intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", BIGINT, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="requested"),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("admin_note", sa.String(500), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("payment_intent_id", name="uq_refund_requests_payment_intent"),
        sa.CheckConstraint("amount > 0", name="ck_refund_requests_amount"),
        sa.CheckConstraint(
            "status IN ('requested', 'requires_manual', 'processing', 'completed', 'rejected')",
            name="ck_refund_requests_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_refund_requests_version"),
    )
    op.create_index("ix_refund_requests_status_created", "refund_requests", ["status", "created_at"])
    op.create_index("ix_refund_requests_order", "refund_requests", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_refund_requests_order", table_name="refund_requests")
    op.drop_index("ix_refund_requests_status_created", table_name="refund_requests")
    op.drop_table("refund_requests")
    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.drop_constraint("ck_merchant_servers_agent_service_status", type_="check")
        batch_op.drop_column("agent_service_status")
        batch_op.drop_column("agent_service_observed_at")
        batch_op.drop_column("agent_service_checks")
    with op.batch_alter_table("payment_intents") as batch_op:
        batch_op.drop_constraint("ck_payment_intents_status", type_="check")
        batch_op.create_check_constraint(
            "ck_payment_intents_status",
            "status IN ('created', 'provider_pending', 'succeeded', 'failed', 'cancelled', 'expired')",
        )
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("ck_orders_payment_status", type_="check")
        batch_op.create_check_constraint(
            "ck_orders_payment_status",
            "payment_status IN ('not_required', 'pending', 'paid', 'refunded')",
        )
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("ck_products_price_unit", type_="check")
        batch_op.drop_constraint("ck_products_single_server", type_="check")
        batch_op.create_check_constraint("ck_products_total_quantity", "available_quantity > 0")
        batch_op.alter_column("price_unit", server_default="gpu_hour")
