"""Add signed Agent hardware inventory and verification state.

Revision ID: 0017_agent_hardware_inventory
Revises: 0016_mazfu_payments
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0017_agent_hardware_inventory"
down_revision: str | Sequence[str] | None = "0016_mazfu_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.add_column(sa.Column("hardware_inventory", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("hardware_inventory_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("hardware_observed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("hardware_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("hardware_verification_status", sa.String(16), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("hardware_mismatches", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.create_check_constraint(
            "ck_merchant_servers_hardware_verification_status",
            "hardware_verification_status IN ('pending', 'verified', 'mismatch', 'stale', 'unavailable')",
        )


def downgrade() -> None:
    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.drop_constraint("ck_merchant_servers_hardware_verification_status", type_="check")
        batch_op.drop_column("hardware_mismatches")
        batch_op.drop_column("hardware_verification_status")
        batch_op.drop_column("hardware_verified_at")
        batch_op.drop_column("hardware_observed_at")
        batch_op.drop_column("hardware_inventory_hash")
        batch_op.drop_column("hardware_inventory")
