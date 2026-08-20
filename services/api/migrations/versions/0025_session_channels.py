"""Separate browser-cookie and native-app bearer sessions.

Revision ID: 0025_session_channels
Revises: 0024_getdeploying_market_source
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_session_channels"
down_revision = "0024_getdeploying_market_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column("channel", sa.String(length=16), nullable=False, server_default="web")
        )
        batch_op.create_index("ix_sessions_channel", ["channel"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_channel")
        batch_op.drop_column("channel")
