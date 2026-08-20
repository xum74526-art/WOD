"""Add manual supplier withdrawal settlement workflow.

Revision ID: 0019_supplier_withdrawals
Revises: 0018_dedicated_server_refunds
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019_supplier_withdrawals"
down_revision: str | Sequence[str] | None = "0018_dedicated_server_refunds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("ck_notifications_category", type_="check")
        batch_op.create_check_constraint(
            "ck_notifications_category",
            "category IN ('order', 'asset', 'review', 'security', 'team', 'dispute', 'payment', 'system')",
        )
    op.create_table(
        "supplier_withdrawals",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("withdrawal_no", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(24), nullable=False, server_default="requested"),
        sa.Column("payout_method", sa.String(32), nullable=False, server_default="manual_bank_transfer"),
        sa.Column("payout_details_encrypted", sa.Text(), nullable=False),
        sa.Column("payout_account_last4", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("withdrawal_no", name="uq_supplier_withdrawals_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_supplier_withdrawals_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_supplier_withdrawals_amount"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_supplier_withdrawals_currency"),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'paid', 'cancelled')",
            name="ck_supplier_withdrawals_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_supplier_withdrawals_version"),
    )
    op.create_index(
        "ix_supplier_withdrawals_supplier_created",
        "supplier_withdrawals",
        ["supplier_id", "created_at"],
    )
    op.create_index(
        "ix_supplier_withdrawals_status_created",
        "supplier_withdrawals",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_withdrawals_status_created", table_name="supplier_withdrawals")
    op.drop_index("ix_supplier_withdrawals_supplier_created", table_name="supplier_withdrawals")
    op.drop_table("supplier_withdrawals")
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("ck_notifications_category", type_="check")
        batch_op.create_check_constraint(
            "ck_notifications_category",
            "category IN ('order', 'asset', 'review', 'security', 'team', 'dispute', 'system')",
        )
