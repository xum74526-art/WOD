"""Add the index omitted by the legacy hand-written schema update.

Revision ID: 0002_add_ingestion_index
Revises: 0001_current_schema
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op


revision: str = "0002_add_ingestion_index"
down_revision: str | Sequence[str] | None = "0001_current_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_news_articles_ingestion_method",
        "news_articles",
        ["ingestion_method"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_news_articles_ingestion_method", table_name="news_articles")
