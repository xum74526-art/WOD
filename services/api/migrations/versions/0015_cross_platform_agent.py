"""Add cross-platform KAI Agent enrollment and device identity.

Revision ID: 0015_cross_platform_agent
Revises: 0014_server_rental_leases
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_cross_platform_agent"
down_revision: str | Sequence[str] | None = "0014_server_rental_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.add_column(sa.Column("agent_device_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("agent_public_key", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("agent_platform", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("agent_arch", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("agent_hostname", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("agent_capabilities", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("agent_enrolled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("agent_revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_merchant_servers_agent_device_id", ["agent_device_id"])
    op.add_column("agent_commands", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "agent_enrollment_tokens",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("server_id", BIGINT, sa.ForeignKey("merchant_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "token_hash", name="agent_enrollment_tokens_token_hash_key"
        ),
    )
    op.create_index("ix_agent_enrollment_tokens_server_id", "agent_enrollment_tokens", ["server_id"])
    op.create_index("ix_agent_enrollment_tokens_token_hash", "agent_enrollment_tokens", ["token_hash"], unique=True)
    op.create_index("ix_agent_enrollment_tokens_expires_at", "agent_enrollment_tokens", ["expires_at"])
    op.create_index("ix_agent_enrollment_tokens_server_expires", "agent_enrollment_tokens", ["server_id", "expires_at"])

    op.create_table(
        "agent_request_nonces",
        sa.Column("nonce", sa.String(64), primary_key=True),
        sa.Column("server_id", BIGINT, sa.ForeignKey("merchant_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_request_nonces_server_id", "agent_request_nonces", ["server_id"])
    op.create_index("ix_agent_request_nonces_expires", "agent_request_nonces", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_request_nonces_expires", table_name="agent_request_nonces")
    op.drop_index("ix_agent_request_nonces_server_id", table_name="agent_request_nonces")
    op.drop_table("agent_request_nonces")
    op.drop_index("ix_agent_enrollment_tokens_server_expires", table_name="agent_enrollment_tokens")
    op.drop_index("ix_agent_enrollment_tokens_expires_at", table_name="agent_enrollment_tokens")
    op.drop_index("ix_agent_enrollment_tokens_token_hash", table_name="agent_enrollment_tokens")
    op.drop_index("ix_agent_enrollment_tokens_server_id", table_name="agent_enrollment_tokens")
    op.drop_table("agent_enrollment_tokens")
    op.drop_column("agent_commands", "started_at")
    with op.batch_alter_table("merchant_servers") as batch_op:
        batch_op.drop_constraint("uq_merchant_servers_agent_device_id", type_="unique")
        batch_op.drop_column("agent_revoked_at")
        batch_op.drop_column("agent_enrolled_at")
        batch_op.drop_column("agent_capabilities")
        batch_op.drop_column("agent_hostname")
        batch_op.drop_column("agent_arch")
        batch_op.drop_column("agent_platform")
        batch_op.drop_column("agent_public_key")
        batch_op.drop_column("agent_device_id")
