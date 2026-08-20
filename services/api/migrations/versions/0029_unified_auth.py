"""Unify password identities and add Kai OAuth state.

Revision ID: 0029_unified_auth
Revises: 0028_product_images
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_unified_auth"
down_revision = "0028_product_images"
branch_labels = None
depends_on = None


BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "issuer", "subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"], unique=False)
    op.create_index("ix_external_identities_provider", "external_identities", ["provider"], unique=False)

    op.create_table(
        "oauth_login_flows",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("intent", sa.String(16), nullable=False),
        sa.Column("return_to", sa.String(1000), nullable=False, server_default="/"),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('web', 'app')", name="ck_oauth_login_flows_channel"),
        sa.CheckConstraint("intent IN ('login', 'register')", name="ck_oauth_login_flows_intent"),
    )
    op.create_index("ix_oauth_login_flows_channel", "oauth_login_flows", ["channel"], unique=False)
    op.create_index("ix_oauth_login_flows_expires_at", "oauth_login_flows", ["expires_at"], unique=False)

    op.create_table(
        "oauth_login_tickets",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oauth_login_tickets_user_id", "oauth_login_tickets", ["user_id"], unique=False)
    op.create_index("ix_oauth_login_tickets_expires_at", "oauth_login_tickets", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_oauth_login_tickets_expires_at", table_name="oauth_login_tickets")
    op.drop_index("ix_oauth_login_tickets_user_id", table_name="oauth_login_tickets")
    op.drop_table("oauth_login_tickets")
    op.drop_index("ix_oauth_login_flows_expires_at", table_name="oauth_login_flows")
    op.drop_index("ix_oauth_login_flows_channel", table_name="oauth_login_flows")
    op.drop_table("oauth_login_flows")
    op.drop_index("ix_external_identities_provider", table_name="external_identities")
    op.drop_index("ix_external_identities_user_id", table_name="external_identities")
    op.drop_table("external_identities")
