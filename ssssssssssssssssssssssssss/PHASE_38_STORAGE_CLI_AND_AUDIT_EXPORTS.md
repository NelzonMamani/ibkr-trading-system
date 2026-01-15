# PHASE 38 — STORAGE CLI & AUDIT EXPORTS (AUTHORITATIVE)

## Intent
Provide simple, safe operator tooling to inspect stored truth and export audit artifacts.

## Scope
- `src/tools/storage_cli.py` (extend)
- `src/cli/*` (optional minimal entrypoints)
- documentation under `docs/` (optional, but helpful)

## CLI Commands (Minimum)
1. `runs:list` — list recent runs, show run_id, started_at, run_mode, cycles
2. `run:show <run_id>` — show config fingerprint, counts, warnings
3. `cycles:list <run_id>` — list cycles for a run (tick, counts)
4. `events:export <run_id> [--format jsonl|csv]` — export append-only events
5. `records:export <run_id> [--format json|csv]` — export trade_records
6. `reports:generate <run_id> [--daily|--weekly|--cumulative]` — invoke Phase 37 generator

## Safety
- CLI must never call IBKR or broker code.
- Only reads from SQLite.
- If db is missing, print a clear error and exit non-zero.

## Deterministic Export
- JSONL lines sorted by `(tick, timestamp_utc, event_type, source)`
- CSV columns fixed and documented
- Ensure stable ordering

## Definition of Done
- CLI works against `data/ibkr_system.db` or configured path.
- Exports can be consumed by external tools without ambiguity.
- New test `tests/test_storage_cli_epoch4.py` validates basic commands (at least run listing and events export path creation).
