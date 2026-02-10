from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator


def _load_cycle_records(log_dir: Path, cycle_id: str) -> list[dict]:
    log_files = sorted(log_dir.glob("trace_*.jsonl"))
    if not log_files:
        return []
    records: list[dict] = []
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("cycle_id") == cycle_id:
            records.append(record)
    return records


def _reconstruct_chain(records: list[dict], target_stage: str) -> list[str]:
    record_map = {record["event_id"]: record for record in records}
    target = next(
        (record for record in records if record.get("stage") == target_stage), None
    )
    if not target:
        return []
    chain_stages: list[str] = []
    current = target
    visited = set()
    while current and current["event_id"] not in visited:
        visited.add(current["event_id"])
        chain_stages.append(current["stage"])
        parent_id = current.get("parent_event_id")
        if parent_id is None:
            break
        current = record_map.get(parent_id)
    return list(reversed(chain_stages))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M4 traceability semantics.")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write verification JSON output.",
    )
    parser.add_argument(
        "--trace-log-dir",
        default=None,
        help="Optional trace log directory (defaults to temp dir).",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )

    try:
        if args.trace_log_dir:
            log_dir = Path(args.trace_log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            os.environ["TRACE_LOG_DIR"] = str(log_dir)
            orchestrator = CoreOrchestrator()
            orchestrator.run_once()
            records = _load_cycle_records(log_dir, orchestrator._current_cycle_id)
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                os.environ["TRACE_LOG_DIR"] = temp_dir
                orchestrator = CoreOrchestrator()
                orchestrator.run_once()
                records = _load_cycle_records(
                    Path(temp_dir), orchestrator._current_cycle_id
                )
    finally:
        set_config_overrides(None)

    required_fields = {
        "event_id",
        "timestamp",
        "event_type",
        "stage",
        "component",
        "entity_id",
        "parent_event_id",
        "cycle_id",
        "run_mode",
        "strategy",
        "metadata",
    }
    schema_errors: list[str] = []
    parent_errors: list[str] = []
    seen_event_ids: set[str] = set()
    for idx, record in enumerate(records):
        for field in required_fields:
            if field not in record:
                schema_errors.append(f"missing_field:{field}")
        if not record.get("timestamp"):
            schema_errors.append("missing_timestamp")
        if idx == 0:
            if record.get("parent_event_id") is not None:
                parent_errors.append("unexpected_parent_for_root")
        else:
            parent_id = record.get("parent_event_id")
            if parent_id not in seen_event_ids:
                parent_errors.append("parent_not_in_chain")
        seen_event_ids.add(record.get("event_id", ""))

    required_stages = ["UNIVERSE", "WATCHLIST", "FOCUS", "ACTION"]
    stage_set = {record.get("stage") for record in records}
    missing_stages = [stage for stage in required_stages if stage not in stage_set]

    chain = _reconstruct_chain(records, "ACTION")
    reconstruction_ok = True
    last_index = -1
    for stage in required_stages:
        if stage not in chain:
            reconstruction_ok = False
            break
        idx = chain.index(stage)
        if idx <= last_index:
            reconstruction_ok = False
            break
        last_index = idx

    output = {
        "epoch": "M4_TRACEABILITY_SEMANTICS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "required_fields": sorted(required_fields),
        "schema_errors": sorted(set(schema_errors)),
        "parent_chain_errors": sorted(set(parent_errors)),
        "missing_stages": missing_stages,
        "reconstruction_chain": chain,
        "reconstruction_ok": reconstruction_ok,
        "valid": not schema_errors and not parent_errors and not missing_stages and reconstruction_ok,
        "version": "1.0",
    }

    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if output["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
