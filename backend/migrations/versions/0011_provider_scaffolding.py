"""Add payment, KYC, private storage, and ledger scaffolding.

Revision ID: 0011_provider_scaffolding
Revises: 0010_session_devices
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_provider_scaffolding"
down_revision: str | Sequence[str] | None = "0010_session_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("payment_no", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", BIGINT, sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="wallet_recharge"),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("provider", sa.String(32), nullable=False, server_default="disabled"),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_message", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("amount > 0", name="ck_payment_intents_amount"),
        sa.CheckConstraint(
            "status IN ('created', 'provider_pending', 'succeeded', 'failed', 'cancelled', 'expired')",
            name="ck_payment_intents_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_payment_intents_version"),
    )
    op.create_index("ix_payment_intents_payment_no", "payment_intents", ["payment_no"], unique=True)
    op.create_index("ix_payment_intents_user_created", "payment_intents", ["user_id", "created_at"])
    op.create_index("ix_payment_intents_status_updated", "payment_intents", ["status", "updated_at"])

    op.create_table(
        "ledger_accounts",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("account_code", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("normal_side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "owner_user_id", "account_type", "currency", name="uq_ledger_account_owner_type_currency"
        ),
        sa.CheckConstraint(
            "account_type IN ('user_available', 'user_frozen', 'platform_clearing', "
            "'platform_revenue', 'provider_clearing')",
            name="ck_ledger_accounts_type",
        ),
        sa.CheckConstraint("normal_side IN ('debit', 'credit')", name="ck_ledger_accounts_normal_side"),
        sa.CheckConstraint("status IN ('active', 'frozen', 'closed')", name="ck_ledger_accounts_status"),
    )
    op.create_index("ix_ledger_accounts_code", "ledger_accounts", ["account_code"], unique=True)

    op.create_table(
        "ledger_journals",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("journal_no", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="posted"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('posted', 'reversed')", name="ck_ledger_journals_status"),
    )
    op.create_index("ix_ledger_journals_no", "ledger_journals", ["journal_no"], unique=True)
    op.create_index(
        "ix_ledger_journals_reference", "ledger_journals", ["reference_type", "reference_id"]
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("journal_id", BIGINT, sa.ForeignKey("ledger_journals.id"), nullable=False),
        sa.Column("account_id", BIGINT, sa.ForeignKey("ledger_accounts.id"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_ledger_entries_direction"),
        sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount"),
    )
    op.create_index("ix_ledger_entries_journal", "ledger_entries", ["journal_id"])
    op.create_index("ix_ledger_entries_account_created", "ledger_entries", ["account_id", "created_at"])

    op.create_table(
        "kyc_applications",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("provider", sa.String(32), nullable=False, server_default="disabled"),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("verification_type", sa.String(24), nullable=False, server_default="individual"),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="CN"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'rejected', 'expired')",
            name="ck_kyc_applications_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_kyc_applications_version"),
    )
    op.create_index("ix_kyc_applications_user_id", "kyc_applications", ["user_id"], unique=True)
    op.create_index("ix_kyc_applications_status_updated", "kyc_applications", ["status", "updated_at"])

    op.create_table(
        "stored_objects",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("object_no", sa.String(32), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kyc_application_id", BIGINT, sa.ForeignKey("kyc_applications.id"), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="disabled"),
        sa.Column("bucket", sa.String(128), nullable=True),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", BIGINT, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="initiating"),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('kyc_document', 'supplier_document', 'contract', 'delivery_artifact', 'general_private')",
            name="ck_stored_objects_category",
        ),
        sa.CheckConstraint(
            "status IN ('initiating', 'uploading', 'available', 'quarantined', 'failed', 'deleted')",
            name="ck_stored_objects_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_stored_objects_size"),
    )
    op.create_index("ix_stored_objects_object_no", "stored_objects", ["object_no"], unique=True)
    op.create_index("ix_stored_objects_owner_created", "stored_objects", ["owner_user_id", "created_at"])
    op.create_index("ix_stored_objects_status_updated", "stored_objects", ["status", "updated_at"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("stored_object_id", BIGINT, sa.ForeignKey("stored_objects.id"), nullable=False, unique=True),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'uploading', 'completed', 'expired', 'failed')",
            name="ck_upload_sessions_status",
        ),
    )
    op.create_index("ix_upload_sessions_expires", "upload_sessions", ["status", "expires_at"])
    op.create_index("ix_upload_sessions_expires_at", "upload_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_expires_at", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_expires", table_name="upload_sessions")
    op.drop_table("upload_sessions")
    op.drop_index("ix_stored_objects_status_updated", table_name="stored_objects")
    op.drop_index("ix_stored_objects_owner_created", table_name="stored_objects")
    op.drop_index("ix_stored_objects_object_no", table_name="stored_objects")
    op.drop_table("stored_objects")
    op.drop_index("ix_kyc_applications_status_updated", table_name="kyc_applications")
    op.drop_index("ix_kyc_applications_user_id", table_name="kyc_applications")
    op.drop_table("kyc_applications")
    op.drop_index("ix_ledger_entries_account_created", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_journal", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_ledger_journals_reference", table_name="ledger_journals")
    op.drop_index("ix_ledger_journals_no", table_name="ledger_journals")
    op.drop_table("ledger_journals")
    op.drop_index("ix_ledger_accounts_code", table_name="ledger_accounts")
    op.drop_table("ledger_accounts")
    op.drop_index("ix_payment_intents_status_updated", table_name="payment_intents")
    op.drop_index("ix_payment_intents_user_created", table_name="payment_intents")
    op.drop_index("ix_payment_intents_payment_no", table_name="payment_intents")
    op.drop_table("payment_intents")
