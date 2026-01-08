PHASE_20_DATA_PERSISTENCE_AND_AUDIT.md

# PHASE 20 — Data Persistence and Audit (Teaching-First → Production-Ready)

## 0) Purpose
Phase 4 has proven the orchestrator pipeline end-to-end (Scanner → Pattern → Signals → Strategy → Risk → Execution → Exit → Performance → Storage) with deterministic simulation and event replay. **Phase 20 upgrades “StorageEngine = placeholder acknowledgement” into a durable, queryable, auditable persistence layer** suitable for:
- Reconstructing any run/cycle deterministically (audit + replay).
- Producing post-trade analytics and compliance-style records.
- Enabling safe incremental progression from SIM to READONLY to LIVE.

This phase is **not** about improving strategy logic. It is about making system outputs **durable, inspectable, and tamper-evident**.

---

## 1) Current State (Observed From Your Run Output)
### Working
- Orchestrator cycles are stable and continuous (`CYCLE_SLEEP_SECONDS=3`).
- Deterministic event replay is functioning (cycle-scoped + run history).
- TradeRecord is created each cycle and passed into StorageEngine.
- PerformanceRegistry emits PERF_SNAPSHOT and structured aggregates.

### Gaps
- StorageEngine prints/acknowledges but **persists nothing**.
- No stable storage schema/versioning/migrations.
- No durable “run ledger” to link: config → cycles → events → trade records → outcomes.
- No tamper-evidence / audit chain / hash integrity.
- Limited support for offline analysis (query/export).

---

## 2) Scope
### In Scope
1. **Durable persistence** for:
   - Run metadata and resolved config.
   - Cycle metadata (tick, session, timestamps).
   - Events (system event stream).
   - TradeRecord (stage outputs).
   - Trade registry state transitions (opened/protected/closed).
   - TradeOutcome and Performance snapshots.
2. **Audit trail**
   - Immutable append-only event log.
   - Hash chaining per event (optional but recommended).
   - Integrity verification command.
3. **Schema versioning + migrations**
   - Explicit schema version.
   - Migration path for future phases.
4. **Exports**
   - Export run/cycle/trades to JSONL/CSV for analysis.
5. **Tests**
   - Unit tests: writing, reading, replay reconstruction, integrity checks.

### Out of Scope (Explicit)
- Live broker integration details.
- Strategy profitability improvements.
- UI/dashboard (may come later).
- Full-blown data warehouse design.

---

## 3) Design Principles
- **Teaching-first**: storage must be easy to inspect locally.
- **Append-only by default**: avoid overwriting historical truth.
- **Structured, explicit schemas**: no “random dicts” without typing and versioning.
- **Reconstructability**: a run can be rebuilt from persisted events + minimal metadata.
- **Deterministic compatibility**: SIM mode must produce identical persisted and replayed outputs.

---

## 4) Storage Backend Choice
### Recommended Default: SQLite (single file)
- Portable, easy to query, stable, supports indexing.
- Suitable for early production and local development.
- Can later be swapped/extended (Postgres, DuckDB, S3 parquet).

**Default path example**
- `data/ibkr_system.sqlite`
- Plus optional `data/events.jsonl` mirror for human inspection.

---

## 5) Data Model (Minimum Tables)
All tables must include: `created_at`, and where applicable `run_id`, `cycle_id`.

### 5.1 runs
- `run_id` (UUID)
- `started_at`, `ended_at`
- `hostname`, `user`, `app_version`, `git_sha` (if available)
- `run_mode`, `event_replay_mode`
- `resolved_config_json` (full authoritative config)
- `schema_version`

### 5.2 cycles
- `cycle_id` (UUID)
- `run_id`
- `tick`
- `session` (PRE/REGULAR/AFTER)
- `cycle_started_at`, `cycle_ended_at`
- summary counters: `scanner_n`, `patterns_n`, `intents_n`, `risk_n`, `exec_n`, `closed_n`

### 5.3 events (append-only)
- `event_id` (UUID)
- `run_id`, `cycle_id`
- `event_type`, `source`
- `timestamp`
- `payload_json`
- `seq` (monotonic per run)
- `prev_hash`, `event_hash` (for audit chain)

### 5.4 trade_records
- `trade_record_id` (UUID)
- `run_id`, `cycle_id`
- `tick`
- `scanner_output_json`
- `pattern_output_json`
- `strategy_output_json`
- `risk_output_json`
- `execution_output_json`
- `trade_outcomes_json`
- `performance_snapshot_json`

### 5.5 trades (optional but recommended normalized view)
- `trade_id` (UUID)
- `run_id`
- `symbol`
- `trader_type`
- `strategy_name`
- `direction`
- `entry_tick`, `entry_price`
- `exit_tick`, `exit_price`
- `quantity`
- `gross_pnl`, `commission`, `net_pnl`
- `status` (OPEN/CLOSED)
- `pattern_name`
- `opened_at`, `closed_at`

This can be derived from events, but persisting a normalized view accelerates analytics.

---

## 6) Audit Integrity (Hash Chain)
Each event row gets a hash:
- `event_hash = SHA256(prev_hash + canonical_event_json)`
- `prev_hash` for first event = `"GENESIS"`
- Canonical JSON = sorted keys, stable serialization (no python repr, no enum object dumps).

Provide:
- `verify_audit_chain(run_id)` → returns (ok, first_bad_seq, reason)

---

## 7) Serialization Rules (Critical)
To avoid brittle payloads:
- Enums must serialize to `.value`
- Decimals serialize as strings (or quantized numeric) consistently
- datetimes must be ISO-8601 with timezone (UTC strongly preferred)
- No python object repr in persisted JSON

Create a single utility:
- `to_jsonable(obj) -> Any` with exhaustive handling:
  - dataclasses
  - enums
  - Decimal
  - datetime
  - dict/list/tuple
  - fallback: `str(obj)` ONLY if explicitly allowed + flagged

---

## 8) Config Additions
Add to runtime config (with safe defaults):
- `PERSISTENCE_ENABLED` (default True in SIM)
- `PERSISTENCE_BACKEND` (default `"sqlite"`)
- `PERSISTENCE_SQLITE_PATH` (default `data/ibkr_system.sqlite`)
- `PERSISTENCE_JSONL_MIRROR_ENABLED` (default False)
- `AUDIT_HASH_CHAIN_ENABLED` (default True)
- `AUDIT_VERIFY_ON_START` (default False)
- `PERSIST_FLUSH_EACH_CYCLE` (default True)

---

## 9) StorageEngine Responsibilities (New Contract)
### Input
- `TradeRecord` (already exists)
- `cycle_context` (tick, session, timestamps)
- event stream (from EventCollector)
- run metadata (resolved config, run_id)

### Output
- returns a `StorageResult` object:
  - `ok: bool`
  - `run_id`, `cycle_id`, `trade_record_id`
  - counts persisted
  - any warnings (e.g., schema drift keys like your `state_history` warning)

### Behavior
- Create `run_id` once at boot.
- Create `cycle_id` each cycle.
- Persist events first (append-only), then TradeRecord, then optional normalized `trades`.
- Never crash the orchestrator:
  - On persistence failure: log `[STORAGE][ERROR]` and continue in SIM (but mark `ok=False`).

---

## 10) CLI / Developer Commands (Minimal)
Add a small CLI entry (or `python -m`) for:
1. `storage init-db`
2. `storage verify-audit --run-id <id>`
3. `storage export --run-id <id> --format jsonl|csv --out <path>`
4. `storage list-runs`
5. `storage show-run --run-id <id>`

---

## 11) Test Plan (Minimum)
### Unit Tests
- `test_to_jsonable_handles_decimal_datetime_enum_dataclass`
- `test_sqlite_persists_run_cycle_events_trade_record`
- `test_audit_hash_chain_verification_ok`
- `test_audit_hash_chain_detects_tamper`
- `test_replay_can_reconstruct_perf_snapshot_from_persisted_events` (teaching-grade)

### Integration Smoke
- Run `src/main.py` for 3 cycles, assert:
  - DB file exists
  - runs=1
  - cycles>=3
  - events increase monotonically
  - trade_records>=3

---

## 12) Definition of Done (Phase 20)
Phase 20 is done when:
1. Running `src/main.py` produces persisted rows in SQLite for runs/cycles/events/trade_records.
2. A specific `run_id` can be exported to JSONL/CSV.
3. Audit verification passes for an untouched run, and fails if one event payload is modified.
4. Persistence does not break replay; replay can operate from in-memory events as today, and optionally from DB in a follow-up enhancement.
5. No “silent schema drift”: unknown keys produce warnings but do not crash.

---

## 13) Immediate Next Phase After 20 (So You Know What This Enables)
Once persistence is durable:
- Move towards READONLY IBKR ingestion (real market data) while keeping execution disabled.
- Add richer analytics and performance reporting (daily/weekly already scaffolded).
- Add “run comparison” tools and regression testing on strategy outputs.

---

# CODEX IMPLEMENTATION INSTRUCTIONS (Single Block)
You must follow these instructions exactly.

1) Create/modify files only as required to implement Phase 20. Keep changes minimal, consistent with the existing architecture.
2) Implement SQLite persistence as the default backend:
   - Add a new persistence module (e.g., `src/storage/sqlite_store.py`) containing:
     - schema creation
     - insert methods for runs/cycles/events/trade_records
     - indexes
   - Add `src/storage/serialization.py` with `to_jsonable()` and stable JSON dumps.
3) Upgrade `StorageEngine` to:
   - create a `run_id` at boot
   - create `cycle_id` per cycle
   - persist events + traderecord each cycle
   - return a structured `StorageResult`
4) Add audit hash chain:
   - canonical JSON serialization (sorted keys)
   - SHA256 chaining across run seq
   - verification function + CLI command
5) Add config keys with safe defaults:
   - must not change existing runtime behavior when persistence is disabled
6) Add minimal CLI commands under a small entry point (e.g., `src/tools/storage_cli.py`).
7) Add unit tests (pytest) for serialization, persistence, and audit verification.
8) Ensure `python src/main.py` runs without errors in SIM mode and writes to `data/ibkr_system.sqlite`.
9) When done, provide:
   - file list changed/added
   - how to run
   - how to verify persistence
   - how to verify audit chain

END_OF_INSTRUCTIONS