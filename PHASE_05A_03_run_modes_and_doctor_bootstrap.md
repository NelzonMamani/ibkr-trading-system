# PHASE_05A_03_run_modes_and_doctor_bootstrap

Date: 2026-01-15

## Objective
Implement explicit run modes and a “doctor” diagnostic entrypoint, and prove the scanner can run one safe cycle.

## Inputs (Must Read)
- EPOCH_05_GOVERNANCE.md (mode law; console proof)
- MODULE_REQUIREMENTS_core_engine.md
- MODULE_REQUIREMENTS_scanner.md

## Allowed Files (Strict)
- src/core_engine/doctor.py (new)
- src/core_engine/bootstrap.py (new or existing; minimal)
- src/core_engine/orchestrator.py (only to add mode banner if needed)
- src/utils/logging.py
- src/utils/validation.py
- src/scanner/scanner_runner.py (only to support a single-cycle run + prints)

## Tasks
1. Add explicit run modes:
   - SIM
   - READONLY
   - LIVE_1SHARE
   Mode must print as a banner at startup.

2. Implement `doctor` entrypoint:
   - validates imports
   - validates configuration load
   - runs scanner in READONLY for 1 cycle (safe) and exits
   - prints an OK/FAIL summary

3. Implement/confirm scanner single-cycle safe behavior:
   - never crashes on missing data (prints N/A, sets flags)
   - prints TopN, survivors, WatchlistK, FocusM
   - if empty: prints `EMPTY WATCHLIST (valid)` with summarized drop reasons

## Commands (Mandatory)
From repo root:
1. `python -m src.core_engine.doctor`
2. `python -m src.scanner.scanner_runner --mode READONLY --cycles 1`

## Required Console Output (Acceptance Evidence)
- Startup banner includes Mode and Session.
- Doctor prints:
  - Imports: OK
  - Config: OK
  - Scanner cycle: OK
- Scanner runner prints:
  - TopN count
  - Survivors count
  - WatchlistK symbols list
  - FocusM symbols list (or empty valid message)

## Acceptance Checklist
- Both commands execute successfully.
- READONLY mode never places broker orders (only logs “would place”).
- Output is unambiguous: K and M lists are clearly printed.

## Rollback Rule
If implementing doctor requires large refactors, stop and reduce scope; the doctor should be lightweight.

END.
