# PHASE_22_COMPLETE_LIVE_READ_ONLY_MARKET_DATA.md

## Objective
Deliver a working, observable, deterministic read-only market data pipeline that connects to IBKR, requests live (or delayed) market data snapshots, and feeds real bid/ask/last/spread/volume into the Scanner. Enforce hard read-only safety gates, verify Phase 21 intent normalization/deduplication, and provide validation logs at startup, per cycle, and shutdown.

## Architecture
- **Market data client (IBKR, read-only)**: `MarketDataClient` in `src/ibkr/market_data_client.py` uses `ib_insync.IB` to connect, set market data type, qualify contracts, and request snapshot data.
- **Live read-only scanner**: `LiveReadOnlyScanner` in `src/scanner/scanner_live_readonly.py` consumes `MarketDataClient` snapshots and emits `ScannerCandidate` records with real market data fields.
- **Teaching-first orchestration**: `CoreOrchestrator` selects the scanner based on `SCANNER_MODE`, preserves the teaching pipeline, and adds explicit validation checkpoints.
- **Read-only guard**: `assert_read_only_allows` in `src/ibkr/read_only_guard.py` hard-blocks any IBKR order action when `IBKR_READONLY_ENABLED=True`.
- **Intent normalization**: the orchestrator stage normalizes/deduplicates `TradeIntent` objects and emits events for observability.

## Config Keys
- `SCANNER_MODE` = `TEACHING` (default) or `LIVE_READONLY`.
- `SCANNER_SYMBOLS` = comma-separated list of symbols (fallback to `IBKR_SCAN_SYMBOLS` for compatibility).
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
- Persisted event counts must match cycle events.
- Validation summary log: `[VALIDATION][SUMMARY] storage=OK intent=OK market_data=OK events=OK`.

### Shutdown
- Active trade registry verification must pass and log `Verification passed — no active trades remain.`

## Definition of Done
- Live read-only scanner prints real bid/ask/last/spread/volume for at least one symbol when market data is available.
- IBKR read-only guard blocks any broker order action and self-test logs `Read-only guard enforced`.
- Intent normalization/dedup is present, emits events, and hard-fails if duplicates remain.
- End-of-cycle validation summary prints all OK.
- Shutdown completes with zero active trades in the registry.

## Test Plan
1. **Teaching mode**
   - `SCANNER_MODE=TEACHING RUN_MODE=SIM python src/main.py`
   - Expect teaching scanner outputs and no crashes.
2. **Live read-only mode**
   - `IBKR_READONLY_ENABLED=True SCANNER_MODE=LIVE_READONLY IBKR_PORT=7497 python src/main.py`
   - Expect IBKR connection, market data type log, `[MD]` lines with bid/ask/last/spread/volume, and read-only guard validation.
3. **Shutdown**
   - Run `python src/main.py`, then press Ctrl+C.
   - Expect clean shutdown logs and registry verification passed.
