"""Add localhost-only direct commerce sandbox.

Revision ID: 0013_local_commerce_sandbox
Revises: 0012_internal_modules
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_local_commerce_sandbox"
down_revision: str | Sequence[str] | None = "0012_internal_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.alter_column("buy_request_id", existing_type=BIGINT, nullable=True)
        batch.alter_column("accepted_quote_id", existing_type=BIGINT, nullable=True)
        batch.add_column(sa.Column("product_id", BIGINT, nullable=True))
        batch.add_column(sa.Column("order_source", sa.String(16), nullable=False, server_default="quote"))
        batch.add_column(sa.Column("environment", sa.String(16), nullable=False, server_default="live"))
        batch.add_column(sa.Column("payment_status", sa.String(24), nullable=False, server_default="not_required"))
        batch.add_column(sa.Column("duration_hours", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_orders_product_id", "products", ["product_id"], ["id"])
        batch.create_check_constraint("ck_orders_source", "order_source IN ('quote', 'direct')")
        batch.create_check_constraint("ck_orders_environment", "environment IN ('live', 'sandbox')")
        batch.create_check_constraint(
            "ck_orders_payment_status",
            "payment_status IN ('not_required', 'pending', 'paid', 'refunded')",
        )
        batch.create_check_constraint(
            "ck_orders_duration_hours",
            "duration_hours IS NULL OR duration_hours > 0",
        )
        batch.create_index("ix_orders_product_created", ["product_id", "created_at"])

    op.create_table(
        "sandbox_instances",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("instance_no", sa.String(32), nullable=False, unique=True),
        sa.Column("order_id", BIGINT, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("runtime", sa.String(32), nullable=False, server_default="local_cpu"),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_seconds", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_sandbox_instances_order"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'stopped')",
            name="ck_sandbox_instances_status",
        ),
        sa.CheckConstraint("run_count >= 0", name="ck_sandbox_instances_run_count"),
        sa.CheckConstraint("usage_seconds >= 0", name="ck_sandbox_instances_usage"),
    )
    op.create_index(
        "ix_sandbox_instances_buyer_status",
        "sandbox_instances",
        ["buyer_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_sandbox_instances_buyer_status", table_name="sandbox_instances")
    op.drop_table("sandbox_instances")
    with op.batch_alter_table("orders") as batch:
        batch.drop_index("ix_orders_product_created")
        batch.drop_constraint("ck_orders_duration_hours", type_="check")
        batch.drop_constraint("ck_orders_payment_status", type_="check")
        batch.drop_constraint("ck_orders_environment", type_="check")
        batch.drop_constraint("ck_orders_source", type_="check")
        batch.drop_constraint("fk_orders_product_id", type_="foreignkey")
        batch.drop_column("duration_hours")
        batch.drop_column("payment_status")
        batch.drop_column("environment")
        batch.drop_column("order_source")
        batch.drop_column("product_id")
        batch.alter_column("accepted_quote_id", existing_type=BIGINT, nullable=False)
        batch.alter_column("buy_request_id", existing_type=BIGINT, nullable=False)
