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
import getpass
import json
import os
import shutil
import sqlite3

from src.config.runtime_config import RunMode, get_persistence_sqlite_path, get_run_mode

AUDIT_LOG_PATH = "data/audit/db_admin_audit.log"
CONFIRM_SAFE_RESET = "SAFE_RESET"
CONFIRM_HARD_RESET = "HARD_RESET"
CONFIRM_RESTORE = "RESTORE_DB"
CONFIRM_PRUNE = "PRUNE_BACKUPS"
DEFAULT_BACKUP_DIR = "data/backups"


def _ensure_audit_log_path() -> str:
    resolved = _resolve_repo_relative_path(AUDIT_LOG_PATH)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    return resolved


def _audit_action(
    action: str,
    target_path: str,
    *,
    run_mode: RunMode | None = None,
    details: dict | None = None,
) -> None:
    payload = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "action": action,
        "target_path": target_path,
        "operator": getpass.getuser(),
        "run_mode": (run_mode or get_run_mode()).value,
        "details": details or {},
    }
    audit_path = _ensure_audit_log_path()
    with open(audit_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    print(f"[DB_ADMIN][AUDIT] {action} recorded in {audit_path}")


def _require_confirmation(confirm_token: str | None, expected: str, action: str) -> None:
    if confirm_token != expected:
        raise ValueError(
            f"[DB_ADMIN][CONFIRM] {action} requires --confirm {expected}"
        )


def _assert_run_mode_safe(allow_live: bool, action: str) -> RunMode:
    run_mode = get_run_mode()
    if run_mode in {RunMode.LIVE, RunMode.READ_ONLY} and not allow_live:
        raise RuntimeError(
            f"[DB_ADMIN][SAFETY] {action} blocked in {run_mode.value} mode. "
            "Pass --allow-live to override."
        )
    return run_mode


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


def safe_reset_database(
    path: str,
    *,
    confirm_token: str | None,
    allow_live: bool = False,
) -> None:
    _require_confirmation(confirm_token, CONFIRM_SAFE_RESET, "Safe reset")
    run_mode = _assert_run_mode_safe(allow_live, "Safe reset")
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
            _audit_action(
                "SAFE_RESET_SKIPPED",
                path,
                run_mode=run_mode,
                details={"reason": "no_tables"},
            )
            return
        table_counts = {}
        for table in tables:
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            table_counts[table] = count
        connection.execute("BEGIN")
        for table in tables:
            connection.execute(f'DELETE FROM "{table}"')
        connection.commit()
    print(f"[DB_ADMIN] Safe reset complete. Deleted rows from {len(tables)} tables.")
    _audit_action(
        "SAFE_RESET",
        path,
        run_mode=run_mode,
        details={"tables": table_counts},
    )


def hard_reset_database(
    path: str,
    *,
    confirm_token: str | None,
    allow_live: bool = False,
) -> None:
    _require_confirmation(confirm_token, CONFIRM_HARD_RESET, "Hard reset")
    run_mode = _assert_run_mode_safe(allow_live, "Hard reset")
    removed = []
    missing = []
    if os.path.exists(path):
        os.remove(path)
        removed.append(path)
        print(f"[DB_ADMIN] Deleted database file: {path}")
    else:
        missing.append(path)
        print(f"[DB_ADMIN] Database file not found: {path}")

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = f"{path}{suffix}"
        if os.path.exists(sidecar):
            os.remove(sidecar)
            removed.append(sidecar)
            print(f"[DB_ADMIN] Deleted sqlite sidecar: {sidecar}")
        else:
            missing.append(sidecar)

    print(
        "[DB_ADMIN] Hard reset complete. The database will be recreated on next startup."
    )
    _audit_action(
        "HARD_RESET",
        path,
        run_mode=run_mode,
        details={"removed": removed, "missing": missing},
    )


def backup_database(
    path: str,
    backup_dir: str | None = None,
    *,
    stamp: str | None = None,
) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQLite database not found at {path}")

    resolved_backup_dir = _resolve_repo_relative_path(
        backup_dir or DEFAULT_BACKUP_DIR
    )
    os.makedirs(resolved_backup_dir, exist_ok=True)
    stamp = stamp or datetime.utcnow().strftime("%Y_%m_%d_%H%M%S")
    filename = f"ibkr_system_{stamp}.db"
    destination = os.path.join(resolved_backup_dir, filename)
    shutil.copy2(path, destination)
    print(f"[DB_ADMIN] Backup created at {destination}")
    _audit_action(
        "BACKUP",
        destination,
        details={"source": path},
    )
    return destination


def restore_database(
    backup_path: str,
    target_path: str,
    *,
    confirm_token: str | None,
    allow_live: bool = False,
    create_backup: bool = True,
) -> str:
    _require_confirmation(confirm_token, CONFIRM_RESTORE, "Restore")
    run_mode = _assert_run_mode_safe(allow_live, "Restore")
    resolved_backup = _resolve_repo_relative_path(backup_path)
    resolved_target = _resolve_repo_relative_path(target_path)
    if not os.path.exists(resolved_backup):
        raise FileNotFoundError(f"Backup file not found: {resolved_backup}")

    os.makedirs(os.path.dirname(resolved_target), exist_ok=True)
    preexisting_backup = None
    if os.path.exists(resolved_target) and create_backup:
        stamp = datetime.utcnow().strftime("%Y_%m_%d_%H%M%S")
        resolved_backup_dir = _resolve_repo_relative_path(DEFAULT_BACKUP_DIR)
        os.makedirs(resolved_backup_dir, exist_ok=True)
        preexisting_backup = os.path.join(
            resolved_backup_dir, f"pre_restore_{stamp}.db"
        )
        shutil.copy2(resolved_target, preexisting_backup)
        print(f"[DB_ADMIN] Pre-restore backup created at {preexisting_backup}")

    shutil.copy2(resolved_backup, resolved_target)
    print(f"[DB_ADMIN] Restore complete. Restored {resolved_backup} to {resolved_target}")
    _audit_action(
        "RESTORE",
        resolved_target,
        run_mode=run_mode,
        details={
            "backup": resolved_backup,
            "pre_restore_backup": preexisting_backup,
        },
    )
    return resolved_target


def prune_backups(
    backup_dir: str | None,
    *,
    retain: int,
    confirm_token: str | None,
    allow_live: bool = False,
) -> list[str]:
    _require_confirmation(confirm_token, CONFIRM_PRUNE, "Prune backups")
    run_mode = _assert_run_mode_safe(allow_live, "Prune backups")
    resolved_backup_dir = _resolve_repo_relative_path(
        backup_dir or DEFAULT_BACKUP_DIR
    )
    if not os.path.exists(resolved_backup_dir):
        raise FileNotFoundError(f"Backup directory not found: {resolved_backup_dir}")
    if retain < 1:
        raise ValueError("Retain must be >= 1")
    backups = [
        os.path.join(resolved_backup_dir, name)
        for name in os.listdir(resolved_backup_dir)
        if name.startswith("ibkr_system_") and name.endswith(".db")
    ]
    backups.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    to_delete = backups[retain:]
    for path in to_delete:
        os.remove(path)
        print(f"[DB_ADMIN] Pruned backup: {path}")
    _audit_action(
        "PRUNE_BACKUPS",
        resolved_backup_dir,
        run_mode=run_mode,
        details={"deleted": to_delete, "retained": backups[:retain]},
    )
    return to_delete


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
    reset_parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required confirmation token ({CONFIRM_SAFE_RESET} or {CONFIRM_HARD_RESET})",
    )
    reset_parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow reset in LIVE/READ_ONLY modes (requires explicit operator intent)",
    )

    subparsers.add_parser(
        "backup",
        help="Copy the database to a dated backup file",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore a database from a backup file",
    )
    restore_parser.add_argument(
        "--backup",
        required=True,
        help="Path to the backup file to restore from",
    )
    restore_parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required confirmation token ({CONFIRM_RESTORE})",
    )
    restore_parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow restore in LIVE/READ_ONLY modes (requires explicit operator intent)",
    )
    restore_parser.add_argument(
        "--no-prebackup",
        action="store_true",
        help="Skip creating a pre-restore backup of the existing DB file",
    )

    prune_parser = subparsers.add_parser(
        "prune-backups",
        help="Prune old backups (explicit, auditable cleanup)",
    )
    prune_parser.add_argument(
        "--retain",
        type=int,
        default=5,
        help="Number of most recent backups to retain",
    )
    prune_parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help="Backup directory to prune",
    )
    prune_parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required confirmation token ({CONFIRM_PRUNE})",
    )
    prune_parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow pruning in LIVE/READ_ONLY modes (requires explicit operator intent)",
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

    if command == "restore":
        restore_database(
            args.backup,
            path,
            confirm_token=args.confirm,
            allow_live=args.allow_live,
            create_backup=not args.no_prebackup,
        )
        return

    if command == "prune-backups":
        prune_backups(
            args.backup_dir,
            retain=args.retain,
            confirm_token=args.confirm,
            allow_live=args.allow_live,
        )
        return

    if command == "reset":
        if getattr(args, "hard", False):
            hard_reset_database(
                path,
                confirm_token=args.confirm,
                allow_live=args.allow_live,
            )
        else:
            safe_reset_database(
                path,
                confirm_token=args.confirm,
                allow_live=args.allow_live,
            )
        return

    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
