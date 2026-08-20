"""Switch the market snapshot default source to GetDeploying.

Revision ID: 0024_getdeploying_market_source
Revises: 0023_market_price_snapshots
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_getdeploying_market_source"
down_revision = "0023_market_price_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("market_price_snapshots") as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=sa.String(length=32),
            server_default="getdeploying",
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("market_price_snapshots") as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=sa.String(length=32),
            server_default="vast_ai",
            existing_nullable=False,
        )
