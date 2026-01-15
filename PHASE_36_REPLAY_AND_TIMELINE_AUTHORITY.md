# PHASE 36 — REPLAY & TIMELINE AUTHORITY (AUTHORITATIVE)

## Intent
Implement a deterministic replay capability driven by stored truth.
Replay is used for:
- learning
- debugging
- audit
- deterministic regression tests

Replay must never access:
- IBKR market data
- broker routing
- network I/O

## Scope
- `src/core/replay_engine.py`
- `src/core/run_event_timeline.py`
- `src/storage/sqlite_store.py` (read APIs)
- `src/events/event_invariants.py` (validation on replay)

## Replay Authority Rules
1. Replay is allowed **only** in `SIM` run mode.
2. Replay is hard-disabled in `LIVE`, `LIVE_READ_ONLY`, and `LIVE_MICRO` regardless of env.
3. Replay data source order:
   1) Stored events for a run/cycle
   2) Stored trade_records for that cycle
   3) Never recompute from live data

## Replay Modes
- `OFF` (default in all live modes)
- `RUN` (replay all cycles for a run_id)
- `CYCLE` (replay a single cycle_id or tick range)

## Timeline Output Contract
`run_event_timeline.py` must produce:
- stable ordering: `(tick, timestamp_utc, event_type, source)`
- optionally grouped by cycle
- optional filters: event_type, source

## Invariants (Replay Validation)
Replay must assert:
- each cycle begins with `CYCLE_START`
- `SCAN_COMPLETE` occurs at most once per cycle per scanner instance
- `EXECUTION_COMPLETE` appears if and only if ExecutionEngine ran (even if it was blocked)
- counts in Cycle summary match the number of stored artifacts
- no event schema violations

## Definition of Done
- StorageEngine stores enough data to replay.
- ReplayEngine can load a stored run and re-emit events deterministically in SIM.
- New tests:
  - `tests/test_replay_from_storage_epoch4.py` (store → load → replay ordering stable)
  - `tests/test_replay_locked_in_live_modes_epoch4.py` (live mode forces OFF)
