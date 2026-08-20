"""Add device metadata and activity tracking to sessions.

Revision ID: 0010_session_devices
Revises: 0009_auth_security
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_session_devices"
down_revision: str | Sequence[str] | None = "0009_auth_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("revoke_reason", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("device_name", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(512), nullable=True))
        batch_op.add_column(sa.Column("ip_address_masked", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("ip_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sessions SET device_name = '历史登录设备', user_agent = '', ip_address_masked = '未知网络', last_seen_at = created_at")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("device_name", existing_type=sa.String(128), nullable=False)
        batch_op.alter_column("user_agent", existing_type=sa.String(512), nullable=False)
        batch_op.alter_column("ip_address_masked", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
        batch_op.create_index("ix_sessions_user_last_seen", ["user_id", "last_seen_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_user_last_seen")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("ip_hash")
        batch_op.drop_column("ip_address_masked")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("device_name")
        batch_op.drop_column("revoke_reason")
