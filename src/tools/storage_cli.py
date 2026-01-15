from __future__ import annotations

import argparse
import os
import sys

from src.config.runtime_config import get_persistence_sqlite_path
from src.performance.storage_reports import generate_reports_from_storage
from src.storage.sqlite_store import SQLiteStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage CLI")
    parser.add_argument(
        "--sqlite-path",
        default=get_persistence_sqlite_path(),
        help="Path to SQLite database",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the storage database")

    runs_list = subparsers.add_parser("runs:list", help="List stored runs")
    runs_list.add_argument("--limit", type=int, default=None)

    run_show = subparsers.add_parser("run:show", help="Show run metadata")
    run_show.add_argument("--run-id", required=True)

    cycles_list = subparsers.add_parser("cycles:list", help="List cycles for a run")
    cycles_list.add_argument("--run-id", required=True)

    events_export = subparsers.add_parser("events:export", help="Export run events")
    events_export.add_argument("--run-id", required=True)
    events_export.add_argument("--format", choices=["jsonl", "csv"], required=True)
    events_export.add_argument("--out", required=True)

    records_export = subparsers.add_parser("records:export", help="Export trade records")
    records_export.add_argument("--run-id", required=True)
    records_export.add_argument("--format", choices=["json", "csv"], required=True)
    records_export.add_argument("--out", required=True)

    reports_generate = subparsers.add_parser(
        "reports:generate",
        help="Generate storage-based performance reports",
    )
    reports_generate.add_argument("--run-id", required=True)
    reports_generate.add_argument("--daily", action="store_true")
    reports_generate.add_argument("--weekly", action="store_true")
    reports_generate.add_argument("--cumulative", action="store_true")

    verify = subparsers.add_parser("verify-audit", help="Verify audit hash chain")
    verify.add_argument("--run-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    sqlite_path = os.path.abspath(args.sqlite_path)
    print(f"[STORAGE] Using SQLite path {sqlite_path}")
    if args.command != "init-db" and not os.path.exists(sqlite_path):
        print(f"[STORAGE][ERROR] SQLite database not found at {sqlite_path}")
        return 2
    store = SQLiteStore(sqlite_path)
    store.initialize_schema()

    try:
        if args.command == "init-db":
            print(f"[STORAGE] Initialized database at {args.sqlite_path}")
            return 0
        if args.command == "runs:list":
            runs = store.list_runs_with_cycle_counts()
            if args.limit is not None:
                runs = runs[-args.limit :]
            for run in runs:
                print(run)
            return 0
        if args.command == "run:show":
            run = store.fetch_run(args.run_id)
            if run is None:
                print(f"[STORAGE] Run not found: {args.run_id}")
                return 1
            print(run)
            return 0
        if args.command == "cycles:list":
            cycles = store.fetch_cycles(args.run_id)
            for cycle in cycles:
                print(cycle)
            return 0
        if args.command == "events:export":
            created = store.export_events(args.run_id, args.format, args.out)
            for path in created:
                print(f"[EXPORT] {path}")
            return 0
        if args.command == "records:export":
            created = store.export_trade_records(args.run_id, args.format, args.out)
            for path in created:
                print(f"[EXPORT] {path}")
            return 0
        if args.command == "reports:generate":
            report_types = []
            if args.daily:
                report_types.append("daily")
            if args.weekly:
                report_types.append("weekly")
            if args.cumulative:
                report_types.append("cumulative")
            if not report_types:
                report_types = ["daily", "weekly", "cumulative"]
            for report_type in report_types:
                artifacts = generate_reports_from_storage(
                    store,
                    args.run_id,
                    report_type,
                )
                print(f"[REPORT] {artifacts.json_path}")
                print(f"[REPORT] {artifacts.text_path}")
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
    finally:
        store.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
