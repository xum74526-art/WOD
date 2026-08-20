"""Persist article and video favorites for the unified community feed.

Revision ID: 0027_content_favorites
Revises: 0026_notification_preferences
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_content_favorites"
down_revision = "0026_notification_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_favorites",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("content_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("content_type IN ('article', 'video')", name="ck_content_favorite_type"),
        sa.UniqueConstraint("user_id", "content_type", "content_id", name="uq_content_favorite_user_item"),
    )
    op.create_index("ix_content_favorites_user_id", "content_favorites", ["user_id"], unique=False)
    op.create_index("ix_content_favorites_user_created", "content_favorites", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_favorites_user_created", table_name="content_favorites")
    op.drop_index("ix_content_favorites_user_id", table_name="content_favorites")
    op.drop_table("content_favorites")
