"""Add SSH-key based server rental leases.

Revision ID: 0014_server_rental_leases
Revises: 0013_local_commerce_sandbox
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014_server_rental_leases"
down_revision: str | Sequence[str] | None = "0013_local_commerce_sandbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "buyer_ssh_keys",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(48), nullable=False),
        sa.Column("fingerprint_sha256", sa.String(128), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("user_id", "fingerprint_sha256", name="uq_buyer_ssh_keys_user_fingerprint"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_buyer_ssh_keys_status"),
        sa.CheckConstraint("version > 0", name="ck_buyer_ssh_keys_version"),
    )
    op.create_index("ix_buyer_ssh_keys_user_status", "buyer_ssh_keys", ["user_id", "status"])

    op.create_table(
        "merchant_servers",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("server_no", sa.String(32), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", BIGINT, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_host", sa.String(255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_username", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="registered"),
        sa.Column("agent_mode", sa.String(24), nullable=False, server_default="local_simulator"),
        sa.Column("agent_certificate_fingerprint", sa.String(128), nullable=True),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("product_id", name="uq_merchant_servers_product"),
        sa.CheckConstraint(
            "status IN ('registered', 'online', 'offline', 'maintenance', 'retired')",
            name="ck_merchant_servers_status",
        ),
        sa.CheckConstraint("ssh_port > 0 AND ssh_port <= 65535", name="ck_merchant_servers_ssh_port"),
        sa.CheckConstraint("version > 0", name="ck_merchant_servers_version"),
    )
    op.create_index("ix_merchant_servers_supplier_status", "merchant_servers", ["supplier_id", "status"])

    op.create_table(
        "access_leases",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("lease_no", sa.String(32), nullable=False, unique=True),
        sa.Column("order_id", BIGINT, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("server_id", BIGINT, sa.ForeignKey("merchant_servers.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ssh_key_id", BIGINT, sa.ForeignKey("buyer_ssh_keys.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_authorization"),
        sa.Column("connection_host", sa.String(255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_username", sa.String(64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("order_id", name="uq_access_leases_order"),
        sa.CheckConstraint(
            "status IN ('pending_authorization', 'active', 'grace', 'expired', 'revoked', 'failed')",
            name="ck_access_leases_status",
        ),
        sa.CheckConstraint("ssh_port > 0 AND ssh_port <= 65535", name="ck_access_leases_ssh_port"),
        sa.CheckConstraint("version > 0", name="ck_access_leases_version"),
    )
    op.create_index("ix_access_leases_buyer_status", "access_leases", ["buyer_id", "status"])
    op.create_index("ix_access_leases_supplier_status", "access_leases", ["supplier_id", "status"])
    op.create_index("ix_access_leases_expiry_status", "access_leases", ["expires_at", "status"])

    op.create_table(
        "agent_commands",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("command_no", sa.String(32), nullable=False, unique=True),
        sa.Column("server_id", BIGINT, sa.ForeignKey("merchant_servers.id"), nullable=False),
        sa.Column("lease_id", BIGINT, sa.ForeignKey("access_leases.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_message", sa.String(500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "action IN ('authorize_key', 'revoke_key', 'cleanup_account')",
            name="ck_agent_commands_action",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_agent_commands_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_agent_commands_attempts"),
    )
    op.create_index("ix_agent_commands_server_status", "agent_commands", ["server_id", "status"])
    op.create_index("ix_agent_commands_lease_created", "agent_commands", ["lease_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_commands_lease_created", table_name="agent_commands")
    op.drop_index("ix_agent_commands_server_status", table_name="agent_commands")
    op.drop_table("agent_commands")
    op.drop_index("ix_access_leases_expiry_status", table_name="access_leases")
    op.drop_index("ix_access_leases_supplier_status", table_name="access_leases")
    op.drop_index("ix_access_leases_buyer_status", table_name="access_leases")
    op.drop_table("access_leases")
    op.drop_index("ix_merchant_servers_supplier_status", table_name="merchant_servers")
    op.drop_table("merchant_servers")
    op.drop_index("ix_buyer_ssh_keys_user_status", table_name="buyer_ssh_keys")
    op.drop_table("buyer_ssh_keys")
