import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from scripts.db_backup_common import (
    MANIFEST_VERSION,
    PgToolRunner,
    database_snapshot,
    ensure_safe_directory,
    postgres_url,
    sha256_file,
    source_summary,
)


def write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def create_backup(output_dir: Path, docker_container: str | None, retention_days: int) -> dict:
    if retention_days < 1:
        raise ValueError("retention-days 必须大于 0")
    url = postgres_url(settings.DATABASE_URL)
    directory = ensure_safe_directory(output_dir)
    created_at = datetime.now(timezone.utc)
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"kai_pg_{url.database}_{stamp}_{uuid.uuid4().hex[:8]}.dump"
    backup_path = directory / backup_name
    partial_path = directory / f".{backup_name}.partial"
    runner = PgToolRunner(url, docker_container)
    revision, counts = database_snapshot(settings.DATABASE_URL)

    descriptor = os.open(partial_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            runner.run(
                "pg_dump",
                [
                    "--format=custom",
                    "--compress=9",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    url.username or "",
                    "--dbname",
                    url.database or "",
                ],
                stdout=output,
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(partial_path, backup_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    checksum = sha256_file(backup_path)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "backup_file": backup_name,
        "format": "postgresql-custom",
        "sha256": checksum,
        "size_bytes": backup_path.stat().st_size,
        "retention_days": retention_days,
        "source": source_summary(url),
        "alembic_revision": revision,
        "critical_table_counts": counts,
        "pg_dump_version": runner.version("pg_dump"),
    }
    write_exclusive(
        backup_path.with_suffix(".manifest.json"),
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    write_exclusive(backup_path.with_suffix(".sha256"), f"{checksum}  {backup_name}\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified KAI PostgreSQL custom-format backup")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--docker-container",
        default=os.getenv("KAI_PG_TOOL_DOCKER_CONTAINER") or os.getenv("WOD_PG_TOOL_DOCKER_CONTAINER"),
    )
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()
    print(json.dumps(create_backup(args.output_dir, args.docker_container, args.retention_days), ensure_ascii=False))


if __name__ == "__main__":
    main()
