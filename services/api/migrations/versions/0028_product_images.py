"""Add product image paths.

Revision ID: 0028_product_images
Revises: 0027_content_favorites
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_product_images"
down_revision = "0027_content_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "image_url")
