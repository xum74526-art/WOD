"""Add confirmation, delivery, cancellation, and version metadata to orders.

Revision ID: 0007_order_lifecycle
Revises: 0006_supplier_review
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_order_lifecycle"
down_revision: str | Sequence[str] | None = "0006_supplier_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("ck_orders_status", type_="check")
        batch_op.add_column(
            sa.Column("buyer_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("supplier_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("delivery_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cancel_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("delivery_note", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_orders_cancelled_by_users",
            "users",
            ["cancelled_by_user_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_orders_status",
            "status IN ('pending_confirmation', 'confirmed', 'delivering', "
            "'delivered', 'completed', 'cancelled')",
        )
        batch_op.create_check_constraint("ck_orders_version", "version > 0")

    orders = sa.table(
        "orders",
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("buyer_confirmed_at", sa.DateTime(timezone=True)),
        sa.column("supplier_confirmed_at", sa.DateTime(timezone=True)),
        sa.column("confirmed_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    connection.execute(
        orders.update().values(buyer_confirmed_at=orders.c.created_at)
    )
    connection.execute(
        orders.update()
        .where(orders.c.status == "confirmed")
        .values(
            supplier_confirmed_at=orders.c.updated_at,
            confirmed_at=orders.c.updated_at,
        )
    )


def downgrade() -> None:
    orders = sa.table("orders", sa.column("status", sa.String()))
    op.get_bind().execute(
        orders.update()
        .where(orders.c.status.in_(("delivering", "delivered", "completed")))
        .values(status="confirmed")
    )
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("ck_orders_version", type_="check")
        batch_op.drop_constraint("ck_orders_status", type_="check")
        batch_op.drop_constraint("fk_orders_cancelled_by_users", type_="foreignkey")
        batch_op.create_check_constraint(
            "ck_orders_status",
            "status IN ('pending_confirmation', 'confirmed', 'cancelled')",
        )
        batch_op.drop_column("version")
        batch_op.drop_column("delivery_note")
        batch_op.drop_column("cancel_reason")
        batch_op.drop_column("cancelled_by_user_id")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("delivered_at")
        batch_op.drop_column("delivery_started_at")
        batch_op.drop_column("confirmed_at")
        batch_op.drop_column("supplier_confirmed_at")
        batch_op.drop_column("buyer_confirmed_at")
