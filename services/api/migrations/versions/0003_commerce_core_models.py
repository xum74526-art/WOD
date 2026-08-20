"""Add the P0 buy request, quote, event, and minimal order models.

Revision ID: 0003_commerce_core
Revises: 0002_add_ingestion_index
Create Date: 2026-08-18
"""
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import math

from alembic import op
import sqlalchemy as sa


revision: str = "0003_commerce_core"
down_revision: str | Sequence[str] | None = "0002_add_ingestion_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _upgrade_buy_requests() -> None:
    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.drop_index("ix_buy_requests_user_id")
        batch_op.alter_column("id", existing_type=sa.Integer(), type_=BIGINT, existing_nullable=False)
        batch_op.alter_column(
            "user_id",
            new_column_name="buyer_id",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "quantity",
            new_column_name="gpu_quantity",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("request_no", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("title", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("visibility", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("min_gpu_memory_gb", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("region_codes", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("delivery_mode", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("budget_amount", sa.Numeric(precision=18, scale=6), nullable=True))
        batch_op.add_column(sa.Column("budget_currency", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("budget_unit", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("quote_deadline_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("expected_start_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("expected_duration_hours", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("requirements", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("close_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=True))

    table = sa.table(
        "buy_requests",
        sa.column("id", BIGINT),
        sa.column("request_type", sa.String()),
        sa.column("gpu_model", sa.String()),
        sa.column("gpu_quantity", sa.Integer()),
        sa.column("cycle_days", sa.Integer()),
        sa.column("budget_ch", sa.Numeric()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("request_no", sa.String()),
        sa.column("title", sa.String()),
        sa.column("visibility", sa.String()),
        sa.column("region_codes", sa.JSON()),
        sa.column("delivery_mode", sa.String()),
        sa.column("budget_amount", sa.Numeric()),
        sa.column("budget_currency", sa.String()),
        sa.column("budget_unit", sa.String()),
        sa.column("quote_deadline_at", sa.DateTime(timezone=True)),
        sa.column("expected_duration_hours", sa.Integer()),
        sa.column("requirements", sa.Text()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("version", sa.Integer()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(table)).mappings().all()
    request_type_aliases = {
        "online": "cloud_compute",
        "remote": "cloud_compute",
        "cloud": "cloud_compute",
        "cloud_compute": "cloud_compute",
        "offline": "offline_device",
        "device": "offline_device",
        "offline_device": "offline_device",
    }
    valid_statuses = {
        "draft",
        "reviewing",
        "published",
        "negotiating",
        "matched",
        "completed",
        "rejected",
        "closed",
        "expired",
    }
    published_statuses = {"published", "negotiating", "matched", "completed"}
    for row in rows:
        created_at = row["created_at"] or datetime.now(timezone.utc)
        deadline = created_at + timedelta(days=7)
        request_type = request_type_aliases.get((row["request_type"] or "").lower(), "cloud_compute")
        status = row["status"] if row["status"] in valid_statuses else "published"
        cycle_days = max(row["cycle_days"] or 1, 1)
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                request_type=request_type,
                status=status,
                request_no=f"BRLEGACY{row['id']:012d}",
                title=f"{row['gpu_model']} 算力求购"[:160],
                visibility="public",
                region_codes=[],
                delivery_mode="remote" if request_type == "cloud_compute" else "negotiable",
                budget_amount=row["budget_ch"],
                budget_currency="CH" if row["budget_ch"] is not None else "USD",
                budget_unit="gpu_hour",
                quote_deadline_at=deadline,
                expected_duration_hours=cycle_days * 24,
                requirements="",
                published_at=created_at if status in published_statuses else None,
                expires_at=deadline if status in published_statuses else None,
                updated_at=created_at,
                version=1,
            )
        )

    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.alter_column("request_no", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("title", existing_type=sa.String(length=160), nullable=False)
        batch_op.alter_column("visibility", existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column("region_codes", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("delivery_mode", existing_type=sa.String(length=24), nullable=False)
        batch_op.alter_column("budget_currency", existing_type=sa.String(length=8), nullable=False)
        batch_op.alter_column("budget_unit", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("quote_deadline_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("requirements", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("version", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("cycle_days")
        batch_op.drop_column("budget_ch")
        batch_op.create_check_constraint(
            "ck_buy_requests_type",
            "request_type IN ('cloud_compute', 'offline_device')",
        )
        batch_op.create_check_constraint(
            "ck_buy_requests_status",
            "status IN ('draft', 'reviewing', 'published', 'negotiating', 'matched', 'completed', 'rejected', 'closed', 'expired')",
        )
        batch_op.create_check_constraint(
            "ck_buy_requests_visibility",
            "visibility IN ('public', 'invited', 'private')",
        )
        batch_op.create_check_constraint(
            "ck_buy_requests_delivery_mode",
            "delivery_mode IN ('remote', 'dedicated', 'negotiable')",
        )
        batch_op.create_check_constraint("ck_buy_requests_gpu_quantity", "gpu_quantity > 0")
        batch_op.create_check_constraint(
            "ck_buy_requests_gpu_memory",
            "min_gpu_memory_gb IS NULL OR min_gpu_memory_gb > 0",
        )
        batch_op.create_check_constraint(
            "ck_buy_requests_budget",
            "budget_amount IS NULL OR budget_amount >= 0",
        )
        batch_op.create_check_constraint(
            "ck_buy_requests_duration",
            "expected_duration_hours IS NULL OR expected_duration_hours > 0",
        )
        batch_op.create_check_constraint("ck_buy_requests_version", "version > 0")
        batch_op.create_index("ix_buy_requests_request_no", ["request_no"], unique=True)
        batch_op.create_index("ix_buy_requests_buyer_id", ["buyer_id"], unique=False)
        batch_op.create_index(
            "ix_buy_requests_public_feed",
            ["status", "visibility", "published_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_buy_requests_quote_deadline",
            ["quote_deadline_at"],
            unique=False,
        )


def _create_commerce_tables() -> None:
    op.create_table(
        "cloud_compute_request_details",
        sa.Column("buy_request_id", BIGINT, nullable=False),
        sa.Column("min_cpu_cores", sa.Integer(), nullable=True),
        sa.Column("min_ram_gb", sa.Integer(), nullable=True),
        sa.Column("min_disk_gb", sa.Integer(), nullable=True),
        sa.Column("min_download_mbps", sa.Integer(), nullable=True),
        sa.Column("public_ip_required", sa.Boolean(), nullable=False),
        sa.Column("container_image", sa.String(length=255), nullable=True),
        sa.Column("software_stack", sa.JSON(), nullable=False),
        sa.Column("special_requirements", sa.Text(), nullable=True),
        sa.CheckConstraint("min_cpu_cores IS NULL OR min_cpu_cores > 0", name="ck_cloud_details_cpu"),
        sa.CheckConstraint("min_ram_gb IS NULL OR min_ram_gb > 0", name="ck_cloud_details_ram"),
        sa.CheckConstraint("min_disk_gb IS NULL OR min_disk_gb > 0", name="ck_cloud_details_disk"),
        sa.CheckConstraint(
            "min_download_mbps IS NULL OR min_download_mbps > 0",
            name="ck_cloud_details_download",
        ),
        sa.ForeignKeyConstraint(["buy_request_id"], ["buy_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("buy_request_id"),
    )

    op.create_table(
        "buy_request_contacts",
        sa.Column("buy_request_id", BIGINT, nullable=False),
        sa.Column("contact_name", sa.String(length=64), nullable=False),
        sa.Column("contact_phone_encrypted", sa.Text(), nullable=True),
        sa.Column("contact_email_encrypted", sa.Text(), nullable=True),
        sa.Column("contact_wechat_encrypted", sa.Text(), nullable=True),
        sa.Column("address_encrypted", sa.Text(), nullable=True),
        sa.Column("encryption_key_id", sa.String(length=64), nullable=True),
        sa.Column("visible_after", sa.String(length=24), nullable=False),
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
        sa.CheckConstraint(
            "visible_after IN ('quote_submitted', 'shortlisted', 'accepted', 'manual_grant')",
            name="ck_buy_request_contacts_visibility",
        ),
        sa.ForeignKeyConstraint(["buy_request_id"], ["buy_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("buy_request_id"),
    )

    op.create_table(
        "buy_request_quotes",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("quote_no", sa.String(length=32), nullable=False),
        sa.Column("buy_request_id", BIGINT, nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("price_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("price_currency", sa.String(length=8), nullable=False),
        sa.Column("price_unit", sa.String(length=32), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("delivery_time_hours", sa.Integer(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_description", sa.Text(), nullable=False),
        sa.Column("buyer_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'shortlisted', 'accepted', 'rejected', 'withdrawn', 'expired')",
            name="ck_buy_request_quotes_status",
        ),
        sa.CheckConstraint("price_amount >= 0", name="ck_buy_request_quotes_price"),
        sa.CheckConstraint("available_quantity > 0", name="ck_buy_request_quotes_quantity"),
        sa.CheckConstraint(
            "delivery_time_hours IS NULL OR delivery_time_hours >= 0",
            name="ck_buy_request_quotes_delivery_time",
        ),
        sa.CheckConstraint("version > 0", name="ck_buy_request_quotes_version"),
        sa.ForeignKeyConstraint(["buy_request_id"], ["buy_requests.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("buy_request_id", "supplier_id", name="uq_buy_request_supplier_quote"),
    )
    op.create_index("ix_buy_request_quotes_quote_no", "buy_request_quotes", ["quote_no"], unique=True)
    op.create_index(
        "ix_buy_request_quotes_request_status",
        "buy_request_quotes",
        ["buy_request_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_buy_request_quotes_supplier_status",
        "buy_request_quotes",
        ["supplier_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_buy_request_quotes_valid_until",
        "buy_request_quotes",
        ["valid_until"],
        unique=False,
    )

    op.create_table(
        "buy_request_events",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("buy_request_id", BIGINT, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["buy_request_id"], ["buy_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_buy_request_events_request_created",
        "buy_request_events",
        ["buy_request_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_buy_request_events_event_type",
        "buy_request_events",
        ["event_type"],
        unique=False,
    )

    op.create_table(
        "orders",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("buy_request_id", BIGINT, nullable=False),
        sa.Column("accepted_quote_id", BIGINT, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("price_unit", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'cancelled')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_orders_amount"),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity"),
        sa.ForeignKeyConstraint(["accepted_quote_id"], ["buy_request_quotes.id"]),
        sa.ForeignKeyConstraint(["buy_request_id"], ["buy_requests.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accepted_quote_id", name="uq_orders_accepted_quote_id"),
        sa.UniqueConstraint("buy_request_id", name="uq_orders_buy_request_id"),
    )
    op.create_index("ix_orders_order_no", "orders", ["order_no"], unique=True)
    op.create_index("ix_orders_buyer_status", "orders", ["buyer_id", "status"], unique=False)
    op.create_index("ix_orders_supplier_status", "orders", ["supplier_id", "status"], unique=False)

    op.create_table(
        "order_events",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("order_id", BIGINT, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_events_order_created",
        "order_events",
        ["order_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_order_events_event_type", "order_events", ["event_type"], unique=False)


def upgrade() -> None:
    _upgrade_buy_requests()
    _create_commerce_tables()


def _downgrade_buy_requests() -> None:
    constraint_names = (
        "ck_buy_requests_type",
        "ck_buy_requests_status",
        "ck_buy_requests_visibility",
        "ck_buy_requests_delivery_mode",
        "ck_buy_requests_gpu_quantity",
        "ck_buy_requests_gpu_memory",
        "ck_buy_requests_budget",
        "ck_buy_requests_duration",
        "ck_buy_requests_version",
    )
    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.drop_index("ix_buy_requests_quote_deadline")
        batch_op.drop_index("ix_buy_requests_public_feed")
        batch_op.drop_index("ix_buy_requests_buyer_id")
        batch_op.drop_index("ix_buy_requests_request_no")
        for constraint_name in constraint_names:
            batch_op.drop_constraint(constraint_name, type_="check")
        batch_op.add_column(sa.Column("cycle_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("budget_ch", sa.Numeric(precision=18, scale=4), nullable=True))

    table = sa.table(
        "buy_requests",
        sa.column("id", BIGINT),
        sa.column("request_type", sa.String()),
        sa.column("expected_duration_hours", sa.Integer()),
        sa.column("budget_amount", sa.Numeric()),
        sa.column("budget_currency", sa.String()),
        sa.column("cycle_days", sa.Integer()),
        sa.column("budget_ch", sa.Numeric()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(table)).mappings().all()
    for row in rows:
        duration = row["expected_duration_hours"] or 24
        connection.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                request_type="offline" if row["request_type"] == "offline_device" else "online",
                cycle_days=max(math.ceil(duration / 24), 1),
                budget_ch=row["budget_amount"] if row["budget_currency"] == "CH" else None,
            )
        )

    with op.batch_alter_table("buy_requests") as batch_op:
        batch_op.alter_column("cycle_days", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "buyer_id",
            new_column_name="user_id",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "gpu_quantity",
            new_column_name="quantity",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column("id", existing_type=BIGINT, type_=sa.Integer(), existing_nullable=False)
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("close_reason")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("published_at")
        batch_op.drop_column("requirements")
        batch_op.drop_column("expected_duration_hours")
        batch_op.drop_column("expected_start_at")
        batch_op.drop_column("quote_deadline_at")
        batch_op.drop_column("budget_unit")
        batch_op.drop_column("budget_currency")
        batch_op.drop_column("budget_amount")
        batch_op.drop_column("delivery_mode")
        batch_op.drop_column("region_codes")
        batch_op.drop_column("min_gpu_memory_gb")
        batch_op.drop_column("visibility")
        batch_op.drop_column("title")
        batch_op.drop_column("request_no")
    op.create_index("ix_buy_requests_user_id", "buy_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("order_events")
    op.drop_table("orders")
    op.drop_table("buy_request_events")
    op.drop_table("buy_request_quotes")
    op.drop_table("buy_request_contacts")
    op.drop_table("cloud_compute_request_details")
    _downgrade_buy_requests()
