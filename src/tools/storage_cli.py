from __future__ import annotations

import argparse
import sys

from config.runtime_config import get_persistence_sqlite_path
from storage.sqlite_store import SQLiteStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage CLI")
    parser.add_argument(
        "--sqlite-path",
        default=get_persistence_sqlite_path(),
        help="Path to SQLite database",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the storage database")

    verify = subparsers.add_parser("verify-audit", help="Verify audit hash chain")
    verify.add_argument("--run-id", required=True)

    export = subparsers.add_parser("export", help="Export run data")
    export.add_argument("--run-id", required=True)
    export.add_argument("--format", choices=["jsonl", "csv"], required=True)
    export.add_argument("--out", required=True)

    subparsers.add_parser("list-runs", help="List stored runs")

    show = subparsers.add_parser("show-run", help="Show run metadata")
    show.add_argument("--run-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store = SQLiteStore(args.sqlite_path)
    store.initialize_schema()

    try:
        if args.command == "init-db":
            print(f"[STORAGE] Initialized database at {args.sqlite_path}")
            return 0
        if args.command == "list-runs":
            for run in store.list_runs():
                print(run)
            return 0
        if args.command == "show-run":
            run = store.fetch_run(args.run_id)
            if run is None:
                print(f"[STORAGE] Run not found: {args.run_id}")
                return 1
            print(run)
            return 0
        if args.command == "verify-audit":
            result = store.verify_audit_chain(args.run_id)
            if result.ok:
                print("[AUDIT] OK")
                return 0
            print(
                "[AUDIT] FAILED "
                f"seq={result.first_bad_seq} reason={result.reason}"
            )
            return 2
        if args.command == "export":
            created = store.export_run(args.run_id, args.format, args.out)
            for path in created:
                print(f"[EXPORT] {path}")
            return 0
    finally:
        store.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
