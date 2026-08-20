import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url


MANIFEST_VERSION = 1
SAFE_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
DRILL_DATABASE_SUFFIXES = ("_restore_drill", "_restore_test")
CRITICAL_TABLES = (
    "alembic_version",
    "users",
    "buy_requests",
    "buy_request_quotes",
    "orders",
    "products",
    "inventory_reservations",
    "sessions",
)


def postgres_url(value: str) -> URL:
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL 必须是 PostgreSQL，备份脚本拒绝操作 SQLite")
    if not url.database or not url.username:
        raise ValueError("DATABASE_URL 必须包含数据库名和用户名")
    return url


def source_summary(url: URL) -> dict[str, str | int | None]:
    return {
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_safe_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError("备份目录不能是符号链接，且必须是实际目录")
    return resolved


def database_snapshot(database_url: str) -> tuple[str, dict[str, int]]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names(schema="public"))
            if "alembic_version" not in tables:
                raise RuntimeError("数据库缺少 alembic_version，拒绝生成不可验证备份")
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            counts = {
                table: int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                for table in CRITICAL_TABLES
                if table in tables and table != "alembic_version"
            }
            return str(revision), counts
    finally:
        engine.dispose()


class PgToolRunner:
    def __init__(self, url: URL, docker_container: str | None = None) -> None:
        self.url = url
        self.docker_container = docker_container
        if docker_container and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", docker_container):
            raise ValueError("Docker 容器名称不合法")
        if docker_container and url.host not in {"127.0.0.1", "localhost", "postgres"}:
            raise ValueError("Docker 工具模式只允许本机或 Compose PostgreSQL 地址")

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.url.host:
            env["PGHOST"] = self.url.host
        if self.url.port:
            env["PGPORT"] = str(self.url.port)
        env["PGUSER"] = self.url.username or ""
        if self.url.password:
            env["PGPASSWORD"] = self.url.password
        return env

    def _command(self, tool: str, args: list[str], *, input_stream: bool = False) -> list[str]:
        if self.docker_container:
            command = ["docker", "exec"]
            if input_stream:
                command.append("-i")
            return [*command, self.docker_container, tool, *args]
        if not shutil.which(tool):
            raise RuntimeError(f"找不到 {tool}；请安装 PostgreSQL 客户端或指定 --docker-container")
        return [tool, *args]

    def run(
        self,
        tool: str,
        args: list[str],
        *,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | int | None = None,
        capture_text: bool = False,
    ) -> subprocess.CompletedProcess:
        command = self._command(tool, args, input_stream=stdin is not None)
        return subprocess.run(
            command,
            check=True,
            env=self._environment(),
            stdin=stdin,
            stdout=subprocess.PIPE if capture_text else stdout,
            stderr=subprocess.PIPE,
            text=capture_text,
        )

    def version(self, tool: str) -> str:
        result = self.run(tool, ["--version"], capture_text=True)
        return result.stdout.strip()


def load_and_verify_manifest(backup_path: Path) -> tuple[dict, Path, Path]:
    backup = backup_path.resolve(strict=True)
    if backup.is_symlink() or not backup.is_file():
        raise ValueError("备份必须是普通文件，不能是符号链接")
    manifest_path = backup.with_suffix(".manifest.json")
    checksum_path = backup.with_suffix(".sha256")
    for companion in (manifest_path, checksum_path):
        if companion.is_symlink() or not companion.is_file():
            raise ValueError(f"缺少或拒绝使用备份伴随文件：{companion.name}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("不支持的备份清单版本")
    if manifest.get("backup_file") != backup.name:
        raise ValueError("备份文件名与清单不一致")
    actual = sha256_file(backup)
    expected = manifest.get("sha256")
    checksum_value = checksum_path.read_text(encoding="ascii").split()[0]
    if actual != expected or actual != checksum_value:
        raise ValueError("备份 SHA-256 校验失败")
    return manifest, manifest_path, checksum_path


def parse_created_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("备份时间必须包含时区")
    return parsed.astimezone(timezone.utc)
