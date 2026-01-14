# SYSTEM_STATE
This file is the current authoritative runtime state and phase plan. It must be updated as phases advance.

## Current Authoritative Runtime State
CURRENT_PHASE: 24
SYSTEM_MODE: LIVE_READ_ONLY with MOCK fallback
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED (orders); IBKR API may be connected for market data depending on configuration

## Phase 24 Status (COMPLETE)
Phase 24 finalises the scanner as a fast, deterministic, cache-first intelligence module with
explicit FAST_VIEW / DEEP_VIEW output, drop-ledger, and data-quality flags.
This phase explicitly **deprecates the legacy 54-field hot-path print contract** in favour of
the Phase 24 FAST_VIEW / DEEP_VIEW model.

## Phase 24 Acceptance Boundary
- Scanner work is restricted to src/scanner/
- Scanner is strategy-agnostic and execution-free
- FAST_VIEW printed for Watchlist K
- DEEP_VIEW printed only for Focus M (top 3–5)
- Drop-ledger records exactly one primary drop reason per excluded symbol
- Data-quality flags emitted; scanner never crashes on missing data

Upon successful execution of PHASE_24_CODEX_INSTRUCTIONS_SCANNER_FINALISATION.md,
Phase 24 is marked COMPLETE and Epoch 1 is CLOSED.

Epoch 1 status: CLOSED

## Phase 27 Status (Planned)
Phase 27 will formalise the **Scanner → Orchestrator Canonical Artifact Contract**.
No Phase 27 work may begin until Phase 24 is marked COMPLETE.

## How to Run
- Orchestrator:
  - python -m src.main
- Standalone scanner:
  - python -m src.scanner.scanner_runner

Last updated: 2026-01-15T00:00:00Z
