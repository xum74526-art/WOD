import argparse
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import settings
from scripts.db_backup_common import (
    DRILL_DATABASE_SUFFIXES,
    SAFE_DATABASE_NAME,
    PgToolRunner,
    database_snapshot,
    load_and_verify_manifest,
    postgres_url,
)


def validate_target_database(name: str, source_database: str) -> None:
    if not SAFE_DATABASE_NAME.fullmatch(name):
        raise ValueError("目标数据库名只能使用小写字母、数字和下划线，且最长 63 位")
    if not name.endswith(DRILL_DATABASE_SUFFIXES):
        raise ValueError("恢复目标必须以 _restore_drill 或 _restore_test 结尾")
    if name == source_database:
        raise ValueError("恢复目标不能是源数据库")


def database_exists(database_url: str, database_name: str) -> bool:
    url = postgres_url(database_url)
    admin_engine = create_engine(url.set(database="postgres"), pool_pre_ping=True)
    try:
        with admin_engine.connect() as connection:
            return connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
            ).scalar_one_or_none() is not None
    finally:
        admin_engine.dispose()


def target_database_url(database_url: str, database_name: str) -> str:
    return postgres_url(database_url).set(database=database_name).render_as_string(
        hide_password=False
    )


def restore_backup(backup: Path, target_database: str, docker_container: str | None) -> dict:
    url = postgres_url(settings.DATABASE_URL)
    source_database = url.database or ""
    validate_target_database(target_database, source_database)
    manifest, _, _ = load_and_verify_manifest(backup)
    if manifest.get("source", {}).get("database") != source_database:
        raise ValueError("当前 DATABASE_URL 的数据库与备份源数据库不一致")
    if database_exists(settings.DATABASE_URL, target_database):
        raise ValueError("目标数据库已经存在；脚本拒绝覆盖或清空现有数据库")

    runner = PgToolRunner(url, docker_container)
    with backup.resolve(strict=True).open("rb") as archive:
        runner.run("pg_restore", ["--list"], stdin=archive, stdout=subprocess.DEVNULL)

    runner.run(
        "createdb",
        ["--username", url.username or "", "--template", "template0", target_database],
        stdout=subprocess.DEVNULL,
    )
    try:
        with backup.resolve(strict=True).open("rb") as archive:
            runner.run(
                "pg_restore",
                [
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    url.username or "",
                    "--dbname",
                    target_database,
                ],
                stdin=archive,
                stdout=subprocess.DEVNULL,
            )
    except Exception as exc:
        raise RuntimeError(
            f"恢复失败；隔离数据库 {target_database} 已保留用于排查，脚本不会自动删除"
        ) from exc

    target_url = target_database_url(settings.DATABASE_URL, target_database)
    revision, counts = database_snapshot(target_url)
    if revision != manifest.get("alembic_revision"):
        raise RuntimeError("恢复后的 Alembic revision 与备份清单不一致")
    if counts != manifest.get("critical_table_counts"):
        raise RuntimeError("恢复后的关键表行数与备份清单不一致")
    return {
        "status": "verified",
        "target_database": target_database,
        "alembic_revision": revision,
        "critical_table_counts": counts,
        "sha256": manifest["sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a KAI backup into a new isolated database")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target-database", required=True)
    parser.add_argument(
        "--docker-container",
        default=os.getenv("KAI_PG_TOOL_DOCKER_CONTAINER") or os.getenv("WOD_PG_TOOL_DOCKER_CONTAINER"),
    )
    args = parser.parse_args()
    print(json.dumps(restore_backup(args.backup, args.target_database, args.docker_container), ensure_ascii=False))


if __name__ == "__main__":
    main()
