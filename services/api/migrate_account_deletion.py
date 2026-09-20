"""Explicit, additive account-deletion migration for an existing API database.

Does not import init_db, application settings, sessions, or startup jobs. Run
with the approved DATABASE_URL explicitly set; there is no local DB fallback.
"""

import argparse
import os
from pathlib import Path
import sys

from sqlalchemy import Column, DateTime, String, create_engine, inspect
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.schema import CreateColumn

from app.models.account_deletion import AccountDeletionRequest


class MigrationError(RuntimeError):
    """A fixed, non-sensitive migration failure code."""


_TABLE = AccountDeletionRequest.__table__
_USER_COLUMNS = (
    Column("account_status", String(16), nullable=False, server_default="active"),
    Column("deleted_at", DateTime, nullable=True),
)


def _validate_existing(connection: Connection) -> None:
    schema = inspect(connection)
    if not schema.has_table("users"):
        raise MigrationError("existing_users_table_required")
    if "id" not in {column["name"] for column in schema.get_columns("users")}:
        raise MigrationError("users_id_required")
    if not schema.has_table(_TABLE.name):
        return
    columns = {column["name"] for column in schema.get_columns(_TABLE.name)}
    if not set(_TABLE.columns.keys()).issubset(columns):
        raise MigrationError("incompatible_deletion_table")
    if not any(
        fk["constrained_columns"] == ["user_id"]
        and fk["referred_table"] == "users"
        and fk["referred_columns"] == ["id"]
        for fk in schema.get_foreign_keys(_TABLE.name)
    ):
        raise MigrationError("deletion_user_foreign_key_required")
    unique_keys = schema.get_unique_constraints(_TABLE.name) + [
        index for index in schema.get_indexes(_TABLE.name) if index["unique"]
    ]
    if not any(key["column_names"] == ["ticket_hash"] for key in unique_keys):
        raise MigrationError("deletion_ticket_uniqueness_required")


def migrate_account_deletion(engine: Engine, *, check_only: bool = False) -> list[str]:
    """Return applied changes (or missing schema in check mode), without DML.

    Only the two users columns and the deletion table/indexes are in scope.
    Incompatible existing structures fail closed instead of being rebuilt.
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
        existing = {column["name"] for column in schema.get_columns("users")}
        for column in _USER_COLUMNS:
            if column.name not in existing:
                changes.append(f"users.{column.name}")
                if not check_only:
                    definition = str(CreateColumn(column).compile(dialect=engine.dialect))
                    connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {definition}")
        if not schema.has_table(_TABLE.name):
            changes.append(_TABLE.name)
            if not check_only:
                # Deliberately NOT Base.metadata.create_all: no other model is migrated.
                _TABLE.create(connection)
        else:
            indexes = {index["name"] for index in schema.get_indexes(_TABLE.name)}
            for index in sorted(_TABLE.indexes, key=lambda item: item.name):
                if index.name not in indexes:
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
        changes = migrate_account_deletion(engine, check_only=args.check)
        if args.check and changes:
            print("Account deletion schema missing: " + ", ".join(changes))
            return 1
        print("Account deletion schema ready" + (": " + ", ".join(changes) if changes else " (unchanged)"))
        return 0
    except MigrationError as error:
        print(f"Account deletion migration refused: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        # SQL errors/URLs can contain credentials or row values. Never print them.
        print(f"Account deletion migration failed ({type(error).__name__})", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
