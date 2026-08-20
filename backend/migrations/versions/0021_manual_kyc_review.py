"""Add encrypted manual KYC review fields.

Revision ID: 0021_manual_kyc_review
Revises: 0020_dispute_finance_action
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_manual_kyc_review"
down_revision = "0020_dispute_finance_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.add_column(sa.Column("subject_details_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("subject_identifier_last4", sa.String(length=4), nullable=True))
        batch_op.add_column(sa.Column("declaration_accepted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_kyc_applications_reviewed_by_user",
            "users",
            ["reviewed_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_constraint("fk_kyc_applications_reviewed_by_user", type_="foreignkey")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("declaration_accepted_at")
        batch_op.drop_column("subject_identifier_last4")
        batch_op.drop_column("subject_details_encrypted")
