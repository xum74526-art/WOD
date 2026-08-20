import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.db_backup_common import ensure_safe_directory, load_and_verify_manifest, parse_created_at


def expired_backup_groups(directory: Path, older_than_days: int) -> list[tuple[Path, Path, Path]]:
    if older_than_days < 1:
        raise ValueError("older-than-days 必须大于 0")
    if not directory.exists():
        raise ValueError("备份目录不存在；清理脚本不会自动创建目录")
    backup_dir = ensure_safe_directory(directory)
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    groups = []
    manifest_paths = {
        *backup_dir.glob("kai_pg_*.manifest.json"),
        *backup_dir.glob("wod_pg_*.manifest.json"),
    }
    for manifest_path in sorted(manifest_paths):
        if manifest_path.is_symlink() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if parse_created_at(manifest["created_at"]) >= cutoff:
            continue
        backup_path = backup_dir / manifest.get("backup_file", "")
        verified, verified_manifest, checksum = load_and_verify_manifest(backup_path)
        if verified.get("created_at") != manifest.get("created_at"):
            raise ValueError(f"清单内容不一致：{manifest_path.name}")
        groups.append((backup_path, verified_manifest, checksum))
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely prune verified KAI PostgreSQL backups")
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--older-than-days", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-directory")
    args = parser.parse_args()

    if not args.backup_dir.exists():
        raise ValueError("备份目录不存在；清理脚本不会自动创建目录")
    directory = ensure_safe_directory(args.backup_dir)
    groups = expired_backup_groups(directory, args.older_than_days)
    files = [str(path) for group in groups for path in group]
    if args.apply:
        if args.confirm_directory != str(directory):
            raise ValueError(f"执行删除时必须传入 --confirm-directory {directory}")
        for group in groups:
            for path in group:
                path.unlink()
    print(json.dumps({"applied": args.apply, "directory": str(directory), "files": files}, ensure_ascii=False))


if __name__ == "__main__":
    main()
