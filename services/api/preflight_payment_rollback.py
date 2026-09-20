"""Read-only gate before changing a live database to an older API release.

This command proves only that no known payment/payout workflow is in flight.
It does not prove that a target commit understands the current schema or
preserves the current authorization and duty-separation rules.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool


ACTIVE_WITHDRAWAL_STATUSES = ("reviewing", "manual_payment_pending")
ACTIVE_PAYMENT_ORDER_STATUSES = (
    "pending",
    "paid",
    "review",
    "late_paid_review",
    "refund_pending",
    "refund_unknown",
)
# payment_operations.REFUND_ACTIVE_STATUSES uses these persisted states. There
# is no generic "pending" refund state in the current schema.
ACTIVE_PAYMENT_REFUND_STATUSES = ("preparing", "submitting", "unknown")
ACTIVE_PAYMENT_REFUND_REQUEST_STATUSES = (
    "pending_review",
    "approved",
    "processing",
)

_REQUIRED_SCHEMA = {
    "withdrawal_orders": {"id", "status", "payout_actor_id"},
    "payment_instruction_grants": {"withdrawal_id", "used_at"},
    "payment_orders": {"status"},
    "payment_refunds": {"status"},
    "payment_refund_requests": {"status"},
}


class PaymentRollbackPreflightError(RuntimeError):
    """Safe, non-sensitive failure raised when rollback cannot be assessed."""


@dataclass(frozen=True)
class RollbackBlocker:
    code: str
    count: int


def _status_count(
    connection: Connection,
    table: str,
    statuses: tuple[str, ...],
) -> int:
    statement = text(
        f"SELECT COUNT(*) FROM {table} WHERE status IN :statuses"
    ).bindparams(bindparam("statuses", expanding=True))
    return int(connection.execute(statement, {"statuses": statuses}).scalar_one())


def _verify_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    available_tables = set(inspector.get_table_names())
    for table, required_columns in _REQUIRED_SCHEMA.items():
        if table not in available_tables:
            raise PaymentRollbackPreflightError("required_schema_missing")
        available_columns = {
            column["name"] for column in inspector.get_columns(table)
        }
        if not required_columns.issubset(available_columns):
            raise PaymentRollbackPreflightError("required_schema_missing")


def _enable_read_only_transaction(connection: Connection) -> None:
    dialect = connection.dialect.name
    if dialect == "sqlite":
        connection.exec_driver_sql("PRAGMA query_only=ON")
    elif dialect == "postgresql":
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    else:
        raise PaymentRollbackPreflightError("unsupported_database_dialect")


def inspect_payment_rollback_blockers(engine: Engine) -> tuple[RollbackBlocker, ...]:
    """Return aggregate blockers without selecting identifiers or payloads."""
    with engine.connect() as connection:
        transaction = connection.begin()
        sqlite_read_only = connection.dialect.name == "sqlite"
        try:
            _enable_read_only_transaction(connection)
            _verify_schema(connection)

            withdrawal_count = _status_count(
                connection,
                "withdrawal_orders",
                ACTIVE_WITHDRAWAL_STATUSES,
            )
            unused_grants = int(connection.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM payment_instruction_grants AS grants "
                    "JOIN withdrawal_orders AS withdrawals "
                    "ON withdrawals.id = grants.withdrawal_id "
                    "WHERE withdrawals.status IN :statuses "
                    "AND grants.used_at IS NULL"
                ).bindparams(bindparam("statuses", expanding=True)),
                {"statuses": ACTIVE_WITHDRAWAL_STATUSES},
            ).scalar_one())
            payment_order_count = _status_count(
                connection,
                "payment_orders",
                ACTIVE_PAYMENT_ORDER_STATUSES,
            )
            refund_count = _status_count(
                connection,
                "payment_refunds",
                ACTIVE_PAYMENT_REFUND_STATUSES,
            )
            refund_request_count = _status_count(
                connection,
                "payment_refund_requests",
                ACTIVE_PAYMENT_REFUND_REQUEST_STATUSES,
            )

            candidates = (
                RollbackBlocker("withdrawal_orders_in_flight", withdrawal_count),
                RollbackBlocker("payment_instruction_grants_unused", unused_grants),
                RollbackBlocker("payment_orders_in_flight", payment_order_count),
                RollbackBlocker("payment_refunds_in_flight", refund_count),
                RollbackBlocker(
                    "payment_refund_requests_in_flight",
                    refund_request_count,
                ),
            )
            return tuple(blocker for blocker in candidates if blocker.count)
        finally:
            transaction.rollback()
            if sqlite_read_only:
                # query_only is connection-local. Clear it before a caller's
                # pooled engine can reuse the connection; this does not touch
                # the database file.
                connection.exec_driver_sql("PRAGMA query_only=OFF")
                connection.rollback()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print(
            "[payment-rollback-preflight] refused: database_url_not_explicit",
            file=sys.stderr,
        )
        return 1

    engine: Engine | None = None
    try:
        # Parsing before engine creation prevents an invalid URL from being
        # echoed by a driver error. Never print this value or caught exceptions.
        parsed_url = make_url(database_url)
        if parsed_url.get_backend_name() == "sqlite":
            database_path = parsed_url.database
            if not database_path or database_path == ":memory:" or not Path(
                database_path
            ).expanduser().is_file():
                raise PaymentRollbackPreflightError("database_file_unavailable")
        engine = create_engine(database_url, poolclass=NullPool)
        blockers = inspect_payment_rollback_blockers(engine)
    except PaymentRollbackPreflightError as exc:
        print(f"[payment-rollback-preflight] refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "[payment-rollback-preflight] refused: database_check_failed",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    if blockers:
        summary = ",".join(f"{blocker.code}={blocker.count}" for blocker in blockers)
        print(f"[payment-rollback-preflight] refused: {summary}", file=sys.stderr)
        return 1

    print(
        "[payment-rollback-preflight] no in-flight payment or payout state found; "
        "target-code compatibility still requires static review"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
