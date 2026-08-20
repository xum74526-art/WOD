from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import engine


_alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
_migration_scripts = ScriptDirectory.from_config(_alembic_config)
EXPECTED_MIGRATION_HEADS = tuple(sorted(_migration_scripts.get_heads()))


def database_readiness() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        current_heads = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))

    if current_heads != EXPECTED_MIGRATION_HEADS:
        current = ",".join(current_heads) or "none"
        expected = ",".join(EXPECTED_MIGRATION_HEADS) or "none"
        raise RuntimeError(f"database migration mismatch: current={current}, expected={expected}")

    return {
        "database_status": "ready",
        "migration_revision": ",".join(current_heads),
        "expected_revision": ",".join(EXPECTED_MIGRATION_HEADS),
    }
