"""Administrative database maintenance utilities.

Database lifecycle (authoritative sources):
- Database path is provided by runtime config and resolved relative to repo root.
- Schema definition and bootstrap live in SQLiteStore.initialize_schema.
- StorageEngine initializes SQLiteStore and calls initialize_schema on startup,
  which recreates the database if the file is missing.

This module is intended for manual maintenance only and should not be imported
by live trading paths.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import shutil
import sqlite3

from src.config.runtime_config import get_persistence_sqlite_path


def _find_repo_root() -> str:
    current = os.path.abspath(os.path.dirname(__file__))
    while True:
        marker = os.path.join(current, "SYSTEM_STATE.md")
        if os.path.exists(marker):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(os.path.dirname(__file__))
        current = parent


def _resolve_repo_relative_path(path: str) -> str:
    if os.path.isabs(path):
        return os.path.abspath(path)
    repo_root = _find_repo_root()
    return os.path.abspath(os.path.join(repo_root, path))


def resolve_sqlite_path() -> str:
    raw_path = get_persistence_sqlite_path(default="data/ibkr_system.db")
    resolved = _resolve_repo_relative_path(raw_path)
    if resolved.endswith("ibkr_system.db"):
        legacy = resolved.replace("ibkr_system.db", "ibkr_system.sqlite")
        if not os.path.exists(resolved) and os.path.exists(legacy):
            print(
                "[DB_ADMIN][WARN] Using legacy sqlite filename ibkr_system.sqlite; "
                "consider renaming to ibkr_system.db"
            )
            return legacy
    return resolved


def safe_reset_database(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQLite database not found at {path}")

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        if not tables:
            print("[DB_ADMIN] No user tables found; nothing to delete.")
            return
        connection.execute("BEGIN")
        for table in tables:
            connection.execute(f'DELETE FROM "{table}"')
        connection.commit()
    print(f"[DB_ADMIN] Safe reset complete. Deleted rows from {len(tables)} tables.")


def hard_reset_database(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
        print(f"[DB_ADMIN] Deleted database file: {path}")
    else:
        print(f"[DB_ADMIN] Database file not found: {path}")

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = f"{path}{suffix}"
        if os.path.exists(sidecar):
            os.remove(sidecar)
            print(f"[DB_ADMIN] Deleted sqlite sidecar: {sidecar}")

    print(
        "[DB_ADMIN] Hard reset complete. The database will be recreated on next startup."
    )


def backup_database(path: str, backup_dir: str | None = None) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQLite database not found at {path}")

    resolved_backup_dir = _resolve_repo_relative_path(
        backup_dir or "data/backups"
    )
    os.makedirs(resolved_backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y_%m_%d")
    filename = f"ibkr_system_{stamp}.db"
    destination = os.path.join(resolved_backup_dir, filename)
    shutil.copy2(path, destination)
    print(f"[DB_ADMIN] Backup created at {destination}")
    return destination


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IBKR SQLite database administration")
    subparsers = parser.add_subparsers(dest="command")

    reset_parser = subparsers.add_parser(
        "reset",
        help="Delete all rows from all tables (safe reset)",
    )
    reset_parser.add_argument(
        "--hard",
        action="store_true",
        help="Delete the database file entirely (hard reset)",
    )

    subparsers.add_parser(
        "backup",
        help="Copy the database to a dated backup file",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = resolve_sqlite_path()
    print(f"[DB_ADMIN] Using SQLite path: {path}")

    command = args.command or "reset"
    if command == "backup":
        backup_database(path)
        return

    if command == "reset":
        if getattr(args, "hard", False):
            hard_reset_database(path)
        else:
            safe_reset_database(path)
        return

    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
