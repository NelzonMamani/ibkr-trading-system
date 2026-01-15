# PHASE_05C_02_scanner_state_and_drop_reason_transparency

Date: 2026-01-15

## Objective
Improve scanner transparency and state:
- NEW / CONTINUING / DROPPED classification
- Drop reasons stored and printed as histogram/summary
- Rank changes (optional, if already available)

## Inputs (Must Read)
- MODULE_REQUIREMENTS_scanner.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (watchlist status tracking item 9)
- EPOCH_05_GOVERNANCE.md

## Allowed Files (Strict)
- src/scanner/scanner_runner.py
- src/scanner/scoring.py
- src/scanner/print_contract.py

## Tasks
1. Track symbol status across cycles.
2. Print:
   - new symbols list
   - dropped symbols list + reason summary
3. Ensure drop reasons are structured in the returned artifact as well.

## Commands (Mandatory)
From repo root:
1. `python -m src.scanner.scanner_runner --mode READONLY --cycles 3`

## Acceptance Checklist
- Output clearly shows NEW/CONTINUING/DROPPED.
- Dropped symbols include reason summary.
- No confusion about why symbols leave the list.

END.
