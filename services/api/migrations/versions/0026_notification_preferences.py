"""Persist cross-platform notification preferences.

Revision ID: 0026_notification_preferences
Revises: 0025_session_channels
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_notification_preferences"
down_revision = "0025_session_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("order_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("device_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revenue_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("wallet_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("system_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
