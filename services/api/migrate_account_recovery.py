"""Explicit, additive account-recovery migration for an existing API database.

Does not import init_db, application settings, sessions, or startup jobs. Run
with the approved DATABASE_URL explicitly set; there is no local DB fallback.
"""

import argparse
import os
from pathlib import Path
import sys

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.schema import CreateColumn


class MigrationError(RuntimeError):
    """A fixed, non-sensitive migration failure code."""


_METADATA = MetaData()
_USERS = Table(
    "users",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column("recovery_email", Text, nullable=True),
    Column("recovery_email_fingerprint", String(64), nullable=True),
    Column("recovery_email_verified_at", DateTime, nullable=True),
    Column("auth_version", Integer, nullable=False, server_default=text("0")),
)
_EMAIL_INDEX = Index(
    "ux_users_recovery_email_fingerprint",
    _USERS.c.recovery_email_fingerprint,
    unique=True,
    sqlite_where=text("recovery_email_fingerprint IS NOT NULL"),
    postgresql_where=text("recovery_email_fingerprint IS NOT NULL"),
)
_TABLE = Table(
    "account_recovery_tokens",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("purpose", String(32), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("target_email", Text, nullable=True),
    Column("target_email_fingerprint", String(64), nullable=True),
    Column("auth_version_snapshot", Integer, nullable=False, server_default=text("0")),
    Column("expires_at", DateTime, nullable=False),
    Column("consumed_at", DateTime, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Index("ix_account_recovery_tokens_user_id", "user_id"),
    Index("ix_account_recovery_tokens_purpose", "purpose"),
    Index("ix_account_recovery_tokens_expires_at", "expires_at"),
)
_MAIL_TABLE = Table(
    "account_recovery_mail_outbox",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column(
        "recovery_token_id",
        Integer,
        ForeignKey("account_recovery_tokens.id"),
        nullable=True,
    ),
    Column("kind", String(32), nullable=False),
    Column("recipient_payload", Text, nullable=True),
    Column("token_payload", Text, nullable=True),
    Column("status", String(16), nullable=False, server_default=text("'pending'")),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("available_at", DateTime, nullable=False),
    Column("locked_at", DateTime, nullable=True),
    Column("expires_at", DateTime, nullable=False),
    Column("last_error_code", String(64), nullable=True),
    Column("delivered_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    Index("ix_account_recovery_mail_outbox_user_id", "user_id"),
    Index(
        "ux_account_recovery_mail_outbox_recovery_token_id",
        "recovery_token_id",
        unique=True,
    ),
    Index(
        "ix_account_recovery_mail_outbox_status_available",
        "status",
        "available_at",
    ),
    Index("ix_account_recovery_mail_outbox_expires_at", "expires_at"),
)
_USER_COLUMNS = (
    _USERS.c.recovery_email,
    _USERS.c.recovery_email_fingerprint,
    _USERS.c.recovery_email_verified_at,
    _USERS.c.auth_version,
)


def _named_email_index(connection: Connection) -> dict | None:
    return next(
        (
            index
            for index in inspect(connection).get_indexes("users")
            if index["name"] == _EMAIL_INDEX.name
        ),
        None,
    )


def _validate_existing(connection: Connection) -> None:
    schema = inspect(connection)
    if not schema.has_table("users"):
        raise MigrationError("existing_users_table_required")
    user_columns = {column["name"] for column in schema.get_columns("users")}
    if "id" not in user_columns:
        raise MigrationError("users_id_required")

    existing_email_index = _named_email_index(connection)
    if existing_email_index is not None and (
        existing_email_index.get("column_names") != ["recovery_email_fingerprint"]
        or not existing_email_index.get("unique")
    ):
        raise MigrationError("incompatible_recovery_email_index")

    if "recovery_email_fingerprint" in user_columns:
        duplicate = connection.exec_driver_sql(
            "SELECT 1 FROM users "
            "WHERE recovery_email_fingerprint IS NOT NULL "
            "GROUP BY recovery_email_fingerprint HAVING COUNT(*) > 1 LIMIT 1"
        ).first()
        if duplicate is not None:
            raise MigrationError("duplicate_recovery_email_fingerprint")

    if schema.has_table(_TABLE.name):
        columns = {column["name"] for column in schema.get_columns(_TABLE.name)}
        if not set(_TABLE.columns.keys()).issubset(columns):
            raise MigrationError("incompatible_recovery_token_table")
        if not any(
            foreign_key["constrained_columns"] == ["user_id"]
            and foreign_key["referred_table"] == "users"
            and foreign_key["referred_columns"] == ["id"]
            for foreign_key in schema.get_foreign_keys(_TABLE.name)
        ):
            raise MigrationError("recovery_token_user_foreign_key_required")
        unique_keys = schema.get_unique_constraints(_TABLE.name) + [
            index for index in schema.get_indexes(_TABLE.name) if index["unique"]
        ]
        if not any(key["column_names"] == ["token_hash"] for key in unique_keys):
            raise MigrationError("recovery_token_hash_uniqueness_required")

    if schema.has_table(_MAIL_TABLE.name):
        columns = {
            column["name"] for column in schema.get_columns(_MAIL_TABLE.name)
        }
        if not set(_MAIL_TABLE.columns.keys()).issubset(columns):
            raise MigrationError("incompatible_recovery_mail_outbox_table")
        foreign_keys = schema.get_foreign_keys(_MAIL_TABLE.name)
        required_foreign_keys = (
            (["user_id"], "users", ["id"]),
            (["recovery_token_id"], _TABLE.name, ["id"]),
        )
        for constrained, referred_table, referred_columns in required_foreign_keys:
            if not any(
                foreign_key["constrained_columns"] == constrained
                and foreign_key["referred_table"] == referred_table
                and foreign_key["referred_columns"] == referred_columns
                for foreign_key in foreign_keys
            ):
                raise MigrationError("recovery_mail_outbox_foreign_key_required")
        token_index = next(
            (
                index
                for index in schema.get_indexes(_MAIL_TABLE.name)
                if index["name"]
                == "ux_account_recovery_mail_outbox_recovery_token_id"
            ),
            None,
        )
        if token_index is not None and (
            token_index.get("column_names") != ["recovery_token_id"]
            or not token_index.get("unique")
        ):
            raise MigrationError("incompatible_recovery_mail_token_index")
        duplicate_token_reference = connection.exec_driver_sql(
            "SELECT 1 FROM account_recovery_mail_outbox "
            "WHERE recovery_token_id IS NOT NULL "
            "GROUP BY recovery_token_id HAVING COUNT(*) > 1 LIMIT 1"
        ).first()
        if duplicate_token_reference is not None:
            raise MigrationError("duplicate_recovery_mail_token_reference")


def migrate_account_recovery(engine: Engine, *, check_only: bool = False) -> list[str]:
    """Return applied changes (or missing schema in check mode), without DML.

    Only the four users columns, their non-null unique fingerprint index, and
    the recovery-token/outbox tables and indexes are in scope. Existing
    account data is never backfilled from KAI identities or profile fields.
    """
    if engine.dialect.name not in {"sqlite", "postgresql"}:
        raise MigrationError("unsupported_database_dialect")
    changes: list[str] = []
    with engine.connect() as connection, connection.begin():
        if not check_only and engine.dialect.name == "sqlite":
            # pysqlite otherwise need not start a transaction for DDL.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        _validate_existing(connection)
        if not check_only and engine.dialect.name == "postgresql":
            connection.exec_driver_sql("LOCK TABLE users IN ACCESS EXCLUSIVE MODE")
            _validate_existing(connection)

        schema = inspect(connection)
        existing_columns = {column["name"] for column in schema.get_columns("users")}
        for column in _USER_COLUMNS:
            if column.name not in existing_columns:
                changes.append(f"users.{column.name}")
                if not check_only:
                    definition = str(CreateColumn(column).compile(dialect=engine.dialect))
                    connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {definition}")

        if _named_email_index(connection) is None:
            changes.append(_EMAIL_INDEX.name)
            if not check_only:
                _EMAIL_INDEX.create(connection)

        for table in (_TABLE, _MAIL_TABLE):
            schema = inspect(connection)
            if not schema.has_table(table.name):
                changes.append(table.name)
                if not check_only:
                    # Deliberately NOT Base.metadata.create_all: no unrelated
                    # application model is migrated by this narrow script.
                    table.create(connection)
            else:
                existing_indexes = {
                    index["name"] for index in schema.get_indexes(table.name)
                }
                for index in sorted(table.indexes, key=lambda item: item.name):
                    if index.name not in existing_indexes:
                        changes.append(index.name)
                        if not check_only:
                            index.create(connection)
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only schema readiness check")
    args = parser.parse_args(argv)
    engine = None
    try:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise MigrationError("explicit_database_url_required")
        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            # CLI is for an existing file, never an accidentally created empty DB.
            if not url.database or url.database == ":memory:" or url.query:
                raise MigrationError("existing_sqlite_file_required")
            if not Path(url.database).is_file():
                raise MigrationError("existing_sqlite_file_required")
        engine = create_engine(url)
        changes = migrate_account_recovery(engine, check_only=args.check)
        if args.check and changes:
            print("Account recovery schema missing: " + ", ".join(changes))
            return 1
        print("Account recovery schema ready" + (": " + ", ".join(changes) if changes else " (unchanged)"))
        return 0
    except MigrationError as error:
        print(f"Account recovery migration refused: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        # SQL errors/URLs can contain credentials or row values. Never print them.
        print(f"Account recovery migration failed ({type(error).__name__})", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
