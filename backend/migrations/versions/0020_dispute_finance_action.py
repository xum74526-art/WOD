"""Link dispute decisions to settlement and refund actions.

Revision ID: 0020_dispute_finance_action
Revises: 0019_supplier_withdrawals
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_dispute_finance_action"
down_revision = "0019_supplier_withdrawals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dispute_cases") as batch_op:
        batch_op.add_column(sa.Column("resolution_action", sa.String(length=32), nullable=True))
        batch_op.create_check_constraint(
            "ck_dispute_cases_resolution_action",
            "resolution_action IS NULL OR resolution_action IN ('release_to_supplier', 'refund_buyer')",
        )


def downgrade() -> None:
    with op.batch_alter_table("dispute_cases") as batch_op:
        batch_op.drop_constraint("ck_dispute_cases_resolution_action", type_="check")
        batch_op.drop_column("resolution_action")
