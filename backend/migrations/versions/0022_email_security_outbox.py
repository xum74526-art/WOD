"""Add email verification tokens and transactional email outbox.

Revision ID: 0022_email_security_outbox
Revises: 0021_manual_kyc_review
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_email_security_outbox"
down_revision = "0021_manual_kyc_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index("ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True)
    op.create_index("ix_email_verification_tokens_expires_at", "email_verification_tokens", ["expires_at"])
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="ck_email_outbox_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_email_outbox_attempts"),
    )
    op.create_index("ix_email_outbox_status_next", "email_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status_next", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("ix_email_verification_tokens_expires_at", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_token_hash", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
