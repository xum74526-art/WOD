"""Limit suppliers to one active quote while preserving terminal history.

Revision ID: 0005_active_quote_unique
Revises: 0004_request_updated_default
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_active_quote_unique"
down_revision: str | Sequence[str] | None = "0004_request_updated_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTIVE_QUOTE_PREDICATE = sa.text(
    "status IN ('draft', 'submitted', 'shortlisted', 'accepted')"
)


def upgrade() -> None:
    with op.batch_alter_table("buy_request_quotes") as batch_op:
        batch_op.drop_constraint("uq_buy_request_supplier_quote", type_="unique")
    op.create_index(
        "uq_buy_request_supplier_active_quote",
        "buy_request_quotes",
        ["buy_request_id", "supplier_id"],
        unique=True,
        postgresql_where=ACTIVE_QUOTE_PREDICATE,
        sqlite_where=ACTIVE_QUOTE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_buy_request_supplier_active_quote",
        table_name="buy_request_quotes",
        postgresql_where=ACTIVE_QUOTE_PREDICATE,
        sqlite_where=ACTIVE_QUOTE_PREDICATE,
    )
    with op.batch_alter_table("buy_request_quotes") as batch_op:
        batch_op.create_unique_constraint(
            "uq_buy_request_supplier_quote",
            ["buy_request_id", "supplier_id"],
        )
