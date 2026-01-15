# PHASE 35 — TRADE STORAGE CANONICAL SCHEMA (AUTHORITATIVE)

## Intent
Define and implement the **canonical persisted representation** of system activity:
- configuration resolution
- per-cycle outputs (scanner → patterns → signals → intents → risk → execution → exits)
- event stream (append-only)
- derived performance snapshots (stored, not inferred)

This phase establishes a stable schema foundation for Epoch 4+ reporting and replay.

## Scope (Permitted Changes)
- `src/storage/*` (schema, migrations, writer)
- `src/core/event_collector.py` (event snapshot normalization if needed)
- `src/events/event_schema.py` (schema coverage completeness)
- `src/models/*` only as needed for storage serialization stability

## Non-Scope
- Modify strategies/signals/pattern logic beyond what is required to store existing outputs.
- Any live routing changes.

## Canonical Storage Objects
### 1) Run
Represents one process lifetime.
Required fields:
- `run_id` (uuid)
- `started_at_utc`, `ended_at_utc` (nullable)
- `effective_run_mode`
- `config_fingerprint` (hash of resolved config records)
- `git_commit` (optional), `system_version` (optional)

### 2) Cycle
Represents one orchestrator cycle.
Required fields:
- `cycle_id` (uuid)
- `run_id`
- `tick`
- `started_at_utc`, `ended_at_utc`
- `market_session` (PRE/REGULAR/AFTER/CLOSED)
- `scanner_candidates_count`, `patterns_count`, `signals_count`, `intents_count`, `risk_decisions_count`, `execution_results_count`, `trade_outcomes_count`
- `warnings_json` (list)

### 3) Event (Append-only)
Canonical events are already emitted; this phase ensures the event table is authoritative and schema-validated.
Required fields:
- `event_id` (uuid)
- `run_id`, `cycle_id`, `tick`
- `event_type`, `source`
- `timestamp_utc`
- `payload_json`
- `schema_version` (int) and/or `payload_hash`

### 4) TradeRecord (Teaching Artifact)
Represents a structured snapshot of one cycle’s pipeline outputs.
- store as JSON blob keyed by `run_id/cycle_id/tick`
- must be compressible and schema-stable

### 5) ExecutionResult / TradeOutcome persistence
Define canonical columns:
- status, attempted, fill_status, requested_quantity, filled_quantity, remaining_quantity
- gross_realised_pnl, commissions, slippage_model (if present)
- rejection_reason, rationale

## SQLite Schema (Minimum Viable)
Create / ensure the following tables exist (additive migrations only):
- `runs`
- `cycles`
- `events`
- `trade_records`
- `execution_results`
- `trade_outcomes`
- `performance_snapshots` (optional in Phase 35; required by Phase 37)

## Migration Discipline
- Schema changes must be additive whenever possible.
- Any destructive migration is forbidden in Epoch 4.
- Provide a simple version table: `schema_meta(version int, applied_at_utc text)`

## Deterministic Serialization Rules
- Use `json.dumps(..., sort_keys=True)` when persisting JSON payloads
- Use ISO 8601 UTC timestamps
- Never persist Python object repr
- Ensure floats are serialized consistently (avoid locale)

## Definition of Done
- StorageEngine persists Run/Cycle/Event/TradeRecord deterministically.
- Database created at configured path; schema version stored.
- New unit test: `tests/test_storage_schema_epoch4.py` validates tables and required columns.
- Existing tests continue to pass.
