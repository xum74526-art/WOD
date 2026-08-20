"""Add persistent authentication limits and password reset tokens.

Revision ID: 0009_auth_security
Revises: 0008_resource_inventory
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_auth_security"
down_revision: str | Sequence[str] | None = "0008_resource_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])

    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_auth_rate_limits_attempts"),
        sa.PrimaryKeyConstraint("key_hash"),
    )
    op.create_index("ix_auth_rate_limits_scope", "auth_rate_limits", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limits_scope", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
