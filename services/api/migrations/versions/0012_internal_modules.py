"""Add database-backed account and supplier internal modules.

Revision ID: 0012_internal_modules
Revises: 0011_provider_scaffolding
Create Date: 2026-08-19
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_internal_modules"
down_revision: str | Sequence[str] | None = "0011_provider_scaffolding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "user_addresses",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(32), nullable=False, server_default="常用地址"),
        sa.Column("recipient_name", sa.String(64), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="CN"),
        sa.Column("province", sa.String(64), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("district", sa.String(64), nullable=True),
        sa.Column("address_line", sa.String(255), nullable=False),
        sa.Column("postal_code", sa.String(24), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version > 0", name="ck_user_addresses_version"),
    )
    op.create_index("ix_user_addresses_user_id", "user_addresses", ["user_id"])
    op.create_index("ix_user_addresses_user_created", "user_addresses", ["user_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(24), nullable=False, server_default="system"),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_path", sa.String(256), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('order', 'asset', 'review', 'security', 'team', 'dispute', 'system')",
            name="ck_notifications_category",
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"])

    op.create_table(
        "supplier_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_name", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=False),
        sa.Column("contact_phone", sa.String(32), nullable=False),
        sa.Column("service_regions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("introduction", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version > 0", name="ck_supplier_profiles_version"),
    )

    op.create_table(
        "dispute_cases",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("dispute_no", sa.String(32), nullable=False),
        sa.Column("order_id", BIGINT, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("counterparty_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("attachment_object_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('open', 'under_review', 'resolved', 'rejected', 'cancelled')", name="ck_dispute_cases_status"),
        sa.CheckConstraint("reason IN ('not_delivered', 'service_unavailable', 'configuration_mismatch', 'billing_issue', 'other')", name="ck_dispute_cases_reason"),
        sa.CheckConstraint("version > 0", name="ck_dispute_cases_version"),
    )
    op.create_index("ix_dispute_cases_no", "dispute_cases", ["dispute_no"], unique=True)
    op.create_index("ix_dispute_cases_opened_status", "dispute_cases", ["opened_by_user_id", "status"])
    op.create_index("ix_dispute_cases_order_created", "dispute_cases", ["order_id", "created_at"])

    op.create_table(
        "dispute_events",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("dispute_id", BIGINT, sa.ForeignKey("dispute_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dispute_events_case_created", "dispute_events", ["dispute_id", "created_at"])

    op.create_table(
        "teams",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version > 0", name="ck_teams_version"),
    )
    op.create_index("ix_teams_owner_user_id", "teams", ["owner_user_id"])
    op.create_index("ix_teams_owner_created", "teams", ["owner_user_id", "created_at"])

    op.create_table(
        "team_members",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("team_id", BIGINT, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name="ck_team_members_role"),
        sa.CheckConstraint("status IN ('active', 'removed')", name="ck_team_members_status"),
    )
    op.create_index("ix_team_members_user_status", "team_members", ["user_id", "status"])

    op.create_table(
        "team_invitations",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("team_id", BIGINT, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "email", name="uq_team_invitations_team_email"),
        sa.CheckConstraint("role IN ('admin', 'member', 'viewer')", name="ck_team_invitations_role"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'revoked', 'expired')", name="ck_team_invitations_status"),
    )
    op.create_index("ix_team_invitations_email_status", "team_invitations", ["email", "status"])

    op.create_table(
        "api_credentials",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_api_credentials_status"),
    )
    op.create_index("ix_api_credentials_user_id", "api_credentials", ["user_id"])
    op.create_index("ix_api_credentials_user_created", "api_credentials", ["user_id", "created_at"])
    op.create_index("ix_api_credentials_secret_hash", "api_credentials", ["secret_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_credentials_secret_hash", table_name="api_credentials")
    op.drop_index("ix_api_credentials_user_created", table_name="api_credentials")
    op.drop_index("ix_api_credentials_user_id", table_name="api_credentials")
    op.drop_table("api_credentials")
    op.drop_index("ix_team_invitations_email_status", table_name="team_invitations")
    op.drop_table("team_invitations")
    op.drop_index("ix_team_members_user_status", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_owner_created", table_name="teams")
    op.drop_index("ix_teams_owner_user_id", table_name="teams")
    op.drop_table("teams")
    op.drop_index("ix_dispute_events_case_created", table_name="dispute_events")
    op.drop_table("dispute_events")
    op.drop_index("ix_dispute_cases_order_created", table_name="dispute_cases")
    op.drop_index("ix_dispute_cases_opened_status", table_name="dispute_cases")
    op.drop_index("ix_dispute_cases_no", table_name="dispute_cases")
    op.drop_table("dispute_cases")
    op.drop_table("supplier_profiles")
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_user_addresses_user_created", table_name="user_addresses")
    op.drop_index("ix_user_addresses_user_id", table_name="user_addresses")
    op.drop_table("user_addresses")
