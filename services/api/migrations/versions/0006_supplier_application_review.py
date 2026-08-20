"""Add supplier application review metadata and audit events.

Revision ID: 0006_supplier_review
Revises: 0005_active_quote_unique
Create Date: 2026-08-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_supplier_review"
down_revision: str | Sequence[str] | None = "0005_active_quote_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("supplier_applications") as batch_op:
        batch_op.add_column(sa.Column("reviewed_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_supplier_applications_reviewed_by_users",
            "users",
            ["reviewed_by"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_supplier_applications_status",
            "status IN ('pending', 'approved', 'rejected')",
        )
        batch_op.create_check_constraint(
            "ck_supplier_applications_version",
            "version > 0",
        )
        batch_op.create_index(
            "ix_supplier_applications_status_created",
            ["status", "created_at"],
            unique=False,
        )

    op.create_table(
        "supplier_application_events",
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("actor_role", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_supplier_events_actor",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["supplier_applications.id"],
            name="fk_supplier_events_application",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_supplier_application_events_application_created",
        "supplier_application_events",
        ["application_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_supplier_application_events_event_type",
        "supplier_application_events",
        ["event_type"],
        unique=False,
    )

    applications = sa.table(
        "supplier_applications",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("status", sa.String()),
    )
    events = sa.table(
        "supplier_application_events",
        sa.column("application_id", sa.Integer()),
        sa.column("actor_user_id", sa.Integer()),
        sa.column("actor_role", sa.String()),
        sa.column("event_type", sa.String()),
        sa.column("from_status", sa.String()),
        sa.column("to_status", sa.String()),
        sa.column("note", sa.Text()),
        sa.column("payload", sa.JSON()),
    )
    connection = op.get_bind()
    legacy_rows = connection.execute(sa.select(applications)).mappings().all()
    if legacy_rows:
        connection.execute(events.insert(), [
            {
                "application_id": row["id"],
                "actor_user_id": row["user_id"],
                "actor_role": "system_migration",
                "event_type": "migrated",
                "from_status": None,
                "to_status": row["status"],
                "note": None,
                "payload": {},
            }
            for row in legacy_rows
        ])


def downgrade() -> None:
    op.drop_index(
        "ix_supplier_application_events_event_type",
        table_name="supplier_application_events",
    )
    op.drop_index(
        "ix_supplier_application_events_application_created",
        table_name="supplier_application_events",
    )
    op.drop_table("supplier_application_events")

    with op.batch_alter_table("supplier_applications") as batch_op:
        batch_op.drop_index("ix_supplier_applications_status_created")
        batch_op.drop_constraint("ck_supplier_applications_version", type_="check")
        batch_op.drop_constraint("ck_supplier_applications_status", type_="check")
        batch_op.drop_constraint(
            "fk_supplier_applications_reviewed_by_users",
            type_="foreignkey",
        )
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
