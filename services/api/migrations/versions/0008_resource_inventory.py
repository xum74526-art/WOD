"""Add reviewed resources, price history, and auditable inventory reservations.

Revision ID: 0008_resource_inventory
Revises: 0007_order_lifecycle
Create Date: 2026-08-18
"""
from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa


revision: str = "0008_resource_inventory"
down_revision: str | Sequence[str] | None = "0007_order_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("resource_no", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("gpu_memory_gb", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cpu_cores", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ram_gb", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("disk_gb", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("bandwidth_mbps", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("price_currency", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("price_unit", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=True))

    products = sa.table(
        "products",
        sa.column("id", sa.Integer()),
        sa.column("memory", sa.String()),
        sa.column("available_quantity", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("resource_no", sa.String()),
        sa.column("gpu_memory_gb", sa.Integer()),
        sa.column("description", sa.Text()),
        sa.column("price_currency", sa.String()),
        sa.column("price_unit", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("version", sa.Integer()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(products)).mappings().all()
    valid_statuses = {"draft", "pending_review", "approved", "published", "rejected", "archived"}
    for row in rows:
        memory_match = re.search(r"\d+", row["memory"] or "")
        status = row["status"] if row["status"] in valid_statuses else "draft"
        created_at = row["created_at"]
        connection.execute(
            products.update().where(products.c.id == row["id"]).values(
                resource_no=f"PRLEGACY{row['id']:012d}",
                gpu_memory_gb=int(memory_match.group()) if memory_match else None,
                available_quantity=max(row["available_quantity"] or 0, 1),
                status=status,
                description="",
                price_currency="CH",
                price_unit="gpu_hour",
                published_at=created_at if status == "published" else None,
                updated_at=created_at,
                version=1,
            )
        )

    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column("resource_no", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("price_currency", existing_type=sa.String(length=8), nullable=False)
        batch_op.alter_column("price_unit", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column("version", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_products_reviewed_by_users", "users", ["reviewed_by"], ["id"]
        )
        batch_op.create_check_constraint(
            "ck_products_status",
            "status IN ('draft', 'pending_review', 'approved', 'published', 'rejected', 'archived')",
        )
        batch_op.create_check_constraint(
            "ck_products_total_quantity", "available_quantity > 0"
        )
        batch_op.create_check_constraint("ck_products_unit_price", "unit_price_ch >= 0")
        batch_op.create_check_constraint("ck_products_version", "version > 0")
        batch_op.create_index("ix_products_resource_no", ["resource_no"], unique=True)
        batch_op.create_index(
            "ix_products_status_updated", ["status", "updated_at"], unique=False
        )

    op.create_table(
        "product_price_versions",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("price_unit", sa.String(32), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_product_price_versions_amount"),
        sa.CheckConstraint("version > 0", name="ck_product_price_versions_version"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "version", name="uq_product_price_version"),
    )
    op.create_index("ix_product_price_versions_product_created", "product_price_versions", ["product_id", "created_at"])

    op.create_table(
        "product_review_events",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("actor_role", sa.String(24), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=True),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_review_events_product_created", "product_review_events", ["product_id", "created_at"])
    op.create_index("ix_product_review_events_event_type", "product_review_events", ["event_type"])

    op.create_table(
        "inventory_reservations",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("reservation_no", sa.String(32), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("order_id", BIGINT, nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('reserved', 'allocated', 'released')", name="ck_inventory_reservations_status"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity"),
        sa.CheckConstraint("version > 0", name="ck_inventory_reservations_version"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_inventory_reservations_order"),
        sa.UniqueConstraint("reservation_no", name="uq_inventory_reservations_no"),
    )
    op.create_index("ix_inventory_reservations_product_status", "inventory_reservations", ["product_id", "status"])
    op.create_index("ix_inventory_reservations_supplier_status", "inventory_reservations", ["supplier_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_inventory_reservations_supplier_status", table_name="inventory_reservations")
    op.drop_index("ix_inventory_reservations_product_status", table_name="inventory_reservations")
    op.drop_table("inventory_reservations")
    op.drop_index("ix_product_review_events_event_type", table_name="product_review_events")
    op.drop_index("ix_product_review_events_product_created", table_name="product_review_events")
    op.drop_table("product_review_events")
    op.drop_index("ix_product_price_versions_product_created", table_name="product_price_versions")
    op.drop_table("product_price_versions")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_status_updated")
        batch_op.drop_index("ix_products_resource_no")
        batch_op.drop_constraint("ck_products_version", type_="check")
        batch_op.drop_constraint("ck_products_unit_price", type_="check")
        batch_op.drop_constraint("ck_products_total_quantity", type_="check")
        batch_op.drop_constraint("ck_products_status", type_="check")
        batch_op.drop_constraint("fk_products_reviewed_by_users", type_="foreignkey")
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("published_at")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("review_note")
        batch_op.drop_column("price_unit")
        batch_op.drop_column("price_currency")
        batch_op.drop_column("description")
        batch_op.drop_column("bandwidth_mbps")
        batch_op.drop_column("disk_gb")
        batch_op.drop_column("ram_gb")
        batch_op.drop_column("cpu_cores")
        batch_op.drop_column("gpu_memory_gb")
        batch_op.drop_column("resource_no")
