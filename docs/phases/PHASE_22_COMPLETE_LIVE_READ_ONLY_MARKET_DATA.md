# PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md

## Objective
Enable a live, read-only IBKR market data scanner that pulls real snapshot data (bid/ask/last/volume), feeds it into the scanner pipeline, and reports truthful validation status without implying broker execution. Provide deterministic validation hooks for Phase 21 intent deduplication and clarify read-only semantics.

## Architecture
- **Market data client (IBKR, read-only)**: `MarketDataClient` in `src/ibkr/market_data_client.py` uses `ib_insync.IB` to connect, set market data type, qualify contracts, and request snapshot data.
- **Live read-only scanner**: `LiveReadOnlyScanner` in `src/scanner/scanner_live_readonly.py` consumes `MarketDataClient` snapshots and emits `ScannerCandidate` records with real market data fields.
- **Teaching-first orchestration**: `CoreOrchestrator` selects the scanner based on `SCANNER_MODE`, preserves the teaching pipeline, and adds explicit validation checkpoints.
- **Read-only guard**: `assert_read_only_allows` in `src/ibkr/read_only_guard.py` hard-blocks any IBKR order action when `IBKR_READONLY_ENABLED=True`.
- **Intent normalization**: the orchestrator stage normalizes/deduplicates `TradeIntent` objects and emits events for observability.

## Config Keys
- `SCANNER_MODE` = `TEACHING` (default) or `LIVE_READONLY`.
- `SCANNER_SYMBOLS` = comma-separated list of symbols (fallback to `IBKR_SCAN_SYMBOLS` for compatibility).
- `INTENT_DEDUP_SELFTEST_ENABLED` = `True` to inject a deterministic duplicate intent and prove deduplication drops it.
- `IBKR_READONLY_ENABLED` = `True` to enforce read-only guard and allow read-only IBKR connections.
- `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID` = IBKR gateway connection settings.
- `IBKR_MARKET_DATA_TYPE` = `LIVE` | `DELAYED` | `DELAYED_FROZEN` (mapped to IBKR market data type codes).
- `IBKR_SNAPSHOT_TIMEOUT_SECONDS` = market data snapshot timeout.
- `IBKR_MAX_SYMBOLS_PER_CYCLE` = cap on snapshot symbols per cycle.
- `PERSISTENCE_SQLITE_PATH` = optional storage path (defaults to `data/ibkr_system.db`, with legacy `.sqlite` fallback).

## Data Flow
1. **Startup**
   - Resolve config, run read-only guard self-test, initialize storage, validate IBKR connectivity if `SCANNER_MODE=LIVE_READONLY`.
2. **Cycle (Scanner → Pattern → Signals → Strategy → Intent Normalization → Risk → Execution → Exit → Storage)**
   - Live read-only scanner fetches IBKR market data snapshots for configured symbols.
   - For each symbol, create a `ScannerCandidate` with real bid/ask/last/spread/volume.
   - Strategy intents are normalized and deduplicated before Risk.
   - Storage persists events and records; validations run and summarize cycle health.
3. **Shutdown**
   - Clean shutdown hooks execute; active trade registry must be empty.

## Validations
### Startup (fail fast)
- Config resolved and logged.
- Storage SQLite path opens successfully (or storage disabled).
- If `SCANNER_MODE=LIVE_READONLY`, IBKR connectivity and market data type request are validated.
- Read-only guard self-test verifies that a mock `PLACE_ORDER` action is blocked.

### Per-cycle
- Intent normalization emits `INTENT_NORMALISED` and `INTENT_DROPPED_DUPLICATE` events.
- Deduplication validation log: `[INTENT][VALIDATION] Deduplication OK — before=<n> after=<m> duplicates_dropped=<k>`.
- Validation summary log uses truthful market data status:
  - `market_data=N/A` when `SCANNER_MODE=TEACHING`
  - `market_data=OK` when at least one live snapshot returns bid/ask/last
  - `market_data=DEGRADED` when all live snapshots are empty/timeout
  - `market_data=FAIL` when IBKR connectivity fails (cycle halts)

### Shutdown
- Active trade registry verification must pass and log `Verification passed — no active trades remain.`

## Definition of Done
- Live read-only scanner prints real bid/ask/last/spread/volume for at least one symbol when market data is available.
- IBKR read-only guard blocks any broker order action and self-test logs `Read-only guard enforced`.
- Intent normalization/dedup is present, emits events, and hard-fails if duplicates remain.
- End-of-cycle validation summary prints truthful market_data status.
- Shutdown completes with zero active trades in the registry.

## Run / Verify Instructions
1. **Teaching mode sanity**
   - `SCANNER_MODE=TEACHING RUN_MODE=SIM python src/main.py`
   - Expect teaching scanner outputs and `market_data=N/A` in the validation summary.
2. **Live read-only market data**
   - `SCANNER_MODE=LIVE_READONLY RUN_MODE=SIM IBKR_READONLY_ENABLED=True \
      IBKR_HOST=127.0.0.1 IBKR_PORT=7497 IBKR_CLIENT_ID=7 \
      IBKR_MARKET_DATA_TYPE=LIVE SCANNER_SYMBOLS=AAPL,TSLA,NVDA python src/main.py`
   - Expect `[IBKR][MD]` connection logs, `[MD]` per symbol snapshots, and `market_data=OK` or `DEGRADED`.
3. **Dedup proof**
   - `INTENT_DEDUP_SELFTEST_ENABLED=True SCANNER_MODE=TEACHING RUN_MODE=SIM python src/main.py`
   - Confirm `[INTENT][SELFTEST] injected_duplicates=1 dropped=<k> OK`.
