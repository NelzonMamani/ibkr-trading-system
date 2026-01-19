from __future__ import annotations

import argparse
import json
import sqlite3

from src.config.config_resolver import get_config, set_config_overrides


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump recent regime snapshots")
    parser.add_argument("--limit", type=int, default=20, help="Number of records to show.")
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default=None,
        help="Override SQLite path for the storage engine.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    overrides = {}
    if args.sqlite_path:
        overrides["PERSISTENCE_SQLITE_PATH"] = args.sqlite_path
    if overrides:
        set_config_overrides(overrides)
    sqlite_path = str(get_config("PERSISTENCE_SQLITE_PATH"))
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.execute(
        """
        SELECT cycle_id, tick, regime_snapshot_json, regime_policy_decision_json, created_at
        FROM trade_records
        WHERE regime_snapshot_json IS NOT NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (args.limit,),
    )
    rows = cursor.fetchall()
    for row in rows:
        snapshot = json.loads(row["regime_snapshot_json"] or "{}")
        policy = json.loads(row["regime_policy_decision_json"] or "{}")
        print(
            f"[REGIME_DUMP] cycle_id={row['cycle_id']} tick={row['tick']} "
            f"label={snapshot.get('label')} confidence={snapshot.get('confidence')} "
            f"policy_applied={policy.get('applied')}"
        )
        print(json.dumps({"snapshot": snapshot, "policy": policy}, indent=2, sort_keys=True))
    if not rows:
        print("[REGIME_DUMP] No regime snapshots found.")
    connection.close()


if __name__ == "__main__":
    main()
