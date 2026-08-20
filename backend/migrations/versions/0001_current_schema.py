"""Establish the current KAI schema as the migration baseline.

Revision ID: 0001_current_schema
Revises:
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_current_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("phone_verified", sa.Boolean(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "community_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=24), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url"),
    )

    op.create_table(
        "news_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("feed_url", sa.String(length=1024), nullable=False),
        sa.Column("site_url", sa.String(length=1024), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("is_official", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_url"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "buy_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_type", sa.String(length=24), nullable=False),
        sa.Column("gpu_model", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("cycle_days", sa.Integer(), nullable=False),
        sa.Column("budget_ch", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_buy_requests_user_id", "buy_requests", ["user_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("gpu_model", sa.String(length=64), nullable=False),
        sa.Column("memory", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("unit_price_ch", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=True),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_gpu_model", "products", ["gpu_model"], unique=False)
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.create_table(
        "supplier_applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(length=128), nullable=False),
        sa.Column("contact_name", sa.String(length=64), nullable=False),
        sa.Column("contact_phone", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_supplier_applications_user_id",
        "supplier_applications",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("title_original", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "content_format",
            sa.String(length=16),
            server_default=sa.text("'html'"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_method",
            sa.String(length=24),
            server_default=sa.text("'official_rss'"),
            nullable=False,
        ),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["news_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_url", name="uq_news_articles_normalized_url"),
    )
    op.create_index("ix_news_articles_category", "news_articles", ["category"], unique=False)
    op.create_index("ix_news_articles_collected_at", "news_articles", ["collected_at"], unique=False)
    op.create_index(
        "ix_news_articles_content_fingerprint",
        "news_articles",
        ["content_fingerprint"],
        unique=True,
    )
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"], unique=False)
    op.create_index("ix_news_articles_source_id", "news_articles", ["source_id"], unique=False)
    op.create_index("ix_news_articles_status", "news_articles", ["status"], unique=False)

    op.create_table(
        "article_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("violation_category", sa.String(length=32), nullable=True),
        sa.Column("moderation_note", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_article_comments_article_id", "article_comments", ["article_id"], unique=False)
    op.create_index(
        "ix_article_comments_content_fingerprint",
        "article_comments",
        ["content_fingerprint"],
        unique=False,
    )
    op.create_index("ix_article_comments_created_at", "article_comments", ["created_at"], unique=False)
    op.create_index("ix_article_comments_status", "article_comments", ["status"], unique=False)
    op.create_index("ix_article_comments_user_id", "article_comments", ["user_id"], unique=False)
    op.create_index(
        "ix_article_comments_violation_category",
        "article_comments",
        ["violation_category"],
        unique=False,
    )

    op.create_table(
        "comment_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["comment_id"], ["article_comments.id"]),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_id", "reporter_id", name="uq_comment_reporter"),
    )
    op.create_index("ix_comment_reports_comment_id", "comment_reports", ["comment_id"], unique=False)
    op.create_index("ix_comment_reports_reporter_id", "comment_reports", ["reporter_id"], unique=False)
    op.create_index("ix_comment_reports_status", "comment_reports", ["status"], unique=False)

    op.create_table(
        "comment_restrictions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("restricted_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_comment_restrictions_restricted_until",
        "comment_restrictions",
        ["restricted_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_comment_restrictions_restricted_until", table_name="comment_restrictions")
    op.drop_table("comment_restrictions")

    op.drop_index("ix_comment_reports_status", table_name="comment_reports")
    op.drop_index("ix_comment_reports_reporter_id", table_name="comment_reports")
    op.drop_index("ix_comment_reports_comment_id", table_name="comment_reports")
    op.drop_table("comment_reports")

    op.drop_index("ix_article_comments_violation_category", table_name="article_comments")
    op.drop_index("ix_article_comments_user_id", table_name="article_comments")
    op.drop_index("ix_article_comments_status", table_name="article_comments")
    op.drop_index("ix_article_comments_created_at", table_name="article_comments")
    op.drop_index("ix_article_comments_content_fingerprint", table_name="article_comments")
    op.drop_index("ix_article_comments_article_id", table_name="article_comments")
    op.drop_table("article_comments")

    op.drop_index("ix_news_articles_status", table_name="news_articles")
    op.drop_index("ix_news_articles_source_id", table_name="news_articles")
    op.drop_index("ix_news_articles_published_at", table_name="news_articles")
    op.drop_index("ix_news_articles_content_fingerprint", table_name="news_articles")
    op.drop_index("ix_news_articles_collected_at", table_name="news_articles")
    op.drop_index("ix_news_articles_category", table_name="news_articles")
    op.drop_table("news_articles")

    op.drop_index("ix_supplier_applications_user_id", table_name="supplier_applications")
    op.drop_table("supplier_applications")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_products_supplier_id", table_name="products")
    op.drop_index("ix_products_gpu_model", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_buy_requests_user_id", table_name="buy_requests")
    op.drop_table("buy_requests")

    op.drop_table("news_sources")
    op.drop_table("community_posts")

    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
