# SYSTEM_STATE
This file is the current authoritative runtime state and phase plan. It must be updated as phases advance.

## Current Authoritative Runtime State
CURRENT_PHASE: 27
SYSTEM_MODE: LIVE_READ_ONLY with MOCK fallback
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED (orders); IBKR API may be connected for market data depending on configuration

## Phase 26 Status (Complete)
Phase 26 enforced execution boundary hardening by removing import-time coupling between orchestrator boot
and broker/execution modules. Main boot and continuous loop operate under LIVE_READ_ONLY while preserving
HARD DISABLED execution.

## Phase 27 Objective (Complete)
Phase 27 formalises the **Scanner → Orchestrator Contract** so the orchestrator consumes a single canonical
scanner artifact instead of relying on “conceptual scan” stubs.

### Triggering Evidence (Observed)
- Orchestrator currently logs:
  - `[TEACH] >>> Scanner stage — gather candidates (conceptual).`
- Standalone `scanner_runner` can produce 54-field rows + watchlist artifacts, but orchestrator ingestion is not yet canonical.

## Phase 27 Contract Requirements

### A) Canonical Scanner Artifact
The scanner must produce a single canonical artifact per cycle containing:
- metadata: timestamp, scanner_version, git_sha (if available), provider_source, run_mode
- counts: candidates_count, enriched_count, excluded_count, watchlist_count
- symbol rows: list of `ScannerRow54` (or a serializable representation with the same 54 fields)
- watchlist symbols: ordered list (top N)
- degradation summary: news_degraded_reason (if any), provider fallback reason (if any), top exclusion reasons (if empty)

Artifact format:
- JSON (primary): `output/scanner/scanner_artifact_<timestamp>.json`
- Watchlist (secondary): `output/watchlists/watchlist_RossMomentum_<timestamp>.txt` (already exists)

### B) Orchestrator Consumption
The orchestrator must consume scanner output from ONE place:
- Either call scanner in-process and receive the artifact object; OR
- Read the artifact JSON from disk (teaching/replay friendly)

The orchestrator must log:
- `scanner_artifact_path` (if file-based)
- counts and top exclusion reasons when watchlist_count == 0
- provenance labels (provider_source, price_truth_source_label, news_degraded_reason)

### C) Execution Boundary Preservation
Phase 27 MUST NOT weaken safety:
- Execution remains HARD DISABLED.
- Scanner must remain order-API free.
- LIVE_READ_ONLY must not route orders.
- Orchestrator ingestion must not enable execution.

## Acceptance Criteria for Phase 27
1) `python -m src.main` completes boot and enters loop without ImportError.
2) Each orchestrator cycle produces or reads a scanner artifact and logs the artifact summary.
3) Artifact JSON is always written (even if empty watchlist).
4) When news is degraded or feeds fail, the scanner bypasses news gates as per Phase 24/25 policy.
5) Watchlist file is always written with header counts and empty-watchlist reasons when applicable.

## Known Degradations (Allowed During Phase 27)
- IBKR snapshots may return missing bid/ask/last/volume; must produce flags and continue.
- RSS sources may rate-limit (403/406/420/429); must be summarized and non-blocking.
- Provider may return default/teaching symbols; must be labeled as such.

## How to Run
- Orchestrator:
  - `python -m src.main`
- Standalone scanner_runner:
  - `python -m src.scanner.scanner_runner`
  - `python src/scanner/scanner_runner.py`

Last updated: 2026-01-10T10:29:03Z
