"""E26 deterministic reset + rebuild CLI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from typing import Iterable

from src.runtime.artifact_registry import build_registry, write_registry_snapshot
from src.runtime.bootstrap import bootstrap_runtime, resolve_sqlite_path
from src.runtime.paths import get_data_dir, get_logs_dir, get_output_dir, is_within, resolve_repo_root


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safety_check(paths: Iterable[Path]) -> None:
    repo_root = resolve_repo_root()
    runtime_roots = [repo_root, get_data_dir(), get_logs_dir(), get_output_dir()]
    for path in paths:
        if not any(is_within(path, root) for root in runtime_roots):
            raise RuntimeError(f"Refusing operation outside allowed runtime roots: {path}")


def _remove_contents(root: Path, *, remove_root: bool = False) -> int:
    if not root.exists():
        return 0
    removed = 0
    for child in list(root.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
            removed += 1
        else:
            child.unlink()
            removed += 1
    if remove_root:
        root.rmdir()
    return removed


def _purge(level: str) -> dict[str, int]:
    logs_dir = get_logs_dir()
    output_dir = get_output_dir()
    data_dir = get_data_dir()
    sqlite_path = resolve_sqlite_path()
    _safety_check([logs_dir, output_dir, data_dir, sqlite_path])

    result = {"logs": 0, "output": 0, "db": 0, "caches": 0}
    result["logs"] = _remove_contents(logs_dir)
    result["output"] = _remove_contents(output_dir)

    if level in {"STANDARD", "HARD"} and data_dir.exists():
        for cache in data_dir.rglob("*cache*"):
            if cache.is_file():
                cache.unlink()
                result["caches"] += 1

    if level == "HARD":
        for candidate in [sqlite_path, *(Path(str(sqlite_path) + suffix) for suffix in ("-wal", "-shm", "-journal"))]:
            if candidate.exists():
                candidate.unlink()
                result["db"] += 1
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup(label: str | None = None) -> Path:
    stamp = _utc_stamp()
    archive_name = f"runtime_backup_{label + '_' if label else ''}{stamp}.tar.gz"
    backup_dir = get_data_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive_path = backup_dir / archive_name
    _safety_check([backup_dir, archive_path])

    include_roots = [get_data_dir(), get_output_dir()]
    with tarfile.open(archive_path, "w:gz") as archive:
        for root in include_roots:
            if root.exists():
                archive.add(root, arcname=root.name)

    manifest = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive_path),
        "sha256": _hash_file(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }
    manifest_path = archive_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return archive_path


def _restore(archive: Path, force: bool) -> None:
    _safety_check([archive])
    if not archive.exists():
        raise FileNotFoundError(f"Archive not found: {archive}")
    manifest_path = archive.with_suffix(".manifest.json")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sha256") != _hash_file(archive):
        raise RuntimeError("Archive hash validation failed")

    targets = [get_data_dir(), get_output_dir()]
    _safety_check(targets)
    if not force:
        for target in targets:
            if target.exists() and any(target.iterdir()):
                raise RuntimeError(f"Target is not empty: {target}; use --force")

    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        _remove_contents(target)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(path=resolve_repo_root())


def main() -> int:
    parser = argparse.ArgumentParser(description="E26 runtime regeneration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("bootstrap")

    purge_parser = subparsers.add_parser("purge")
    purge_parser.add_argument("--level", choices=("LIGHT", "STANDARD", "HARD"), required=True)
    purge_parser.add_argument("--confirm", action="store_true")

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--label", default=None)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--archive", required=True)
    restore_parser.add_argument("--force", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot-registry")
    snapshot_parser.add_argument(
        "--out",
        default="AUDIT_EVIDENCE/E26_artifact_registry_snapshot.json",
    )

    args = parser.parse_args()
    if args.command == "bootstrap":
        result = bootstrap_runtime()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "purge":
        if not args.confirm:
            raise SystemExit("purge requires --confirm")
        print(json.dumps({"level": args.level, "removed": _purge(args.level)}, indent=2, sort_keys=True))
        return 0
    if args.command == "backup":
        archive = _backup(label=args.label)
        print(str(archive))
        return 0
    if args.command == "restore":
        _restore(Path(args.archive), force=args.force)
        print("restore complete")
        return 0
    if args.command == "snapshot-registry":
        out = write_registry_snapshot(Path(args.out))
        print(str(out))
        return 0

    _ = build_registry()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
