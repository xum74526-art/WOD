"""Add hourly GPU market price snapshots.

Revision ID: 0023_market_price_snapshots
Revises: 0022_email_security_outbox
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_market_price_snapshots"
down_revision = "0022_email_security_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_price_snapshots",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), server_default="vast_ai", nullable=False),
        sa.Column("gpu_model", sa.String(length=64), nullable=False),
        sa.Column("bucket_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("min_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("median_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("available", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD", nullable=False),
        sa.Column("price_unit", sa.String(length=32), server_default="gpu_hour", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("min_price >= 0", name="ck_market_price_snapshots_min_price"),
        sa.CheckConstraint("median_price >= 0", name="ck_market_price_snapshots_median_price"),
        sa.CheckConstraint("available >= 0", name="ck_market_price_snapshots_available"),
        sa.UniqueConstraint("source", "gpu_model", "bucket_hour", name="uq_market_price_snapshot_hour"),
    )
    op.create_index(
        "ix_market_price_snapshots_model_observed",
        "market_price_snapshots",
        ["gpu_model", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_price_snapshots_model_observed", table_name="market_price_snapshots")
    op.drop_table("market_price_snapshots")
