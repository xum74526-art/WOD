"""Add the missing database default for buy request update timestamps.

Revision ID: 0004_request_updated_default
Revises: 0003_commerce_core
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_request_updated_default"
down_revision: str | Sequence[str] | None = "0003_commerce_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def downgrade() -> None:
    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
