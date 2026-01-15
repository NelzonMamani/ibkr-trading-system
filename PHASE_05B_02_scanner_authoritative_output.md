# PHASE_05B_02_scanner_authoritative_output

Date: 2026-01-15

## Objective
Make the scanner authoritative and operator-grade:
Top N gainers → hard gates → Watchlist K → Focus M (3–5 default; up to 10).
Empty watchlists must be valid and explained.

## Inputs (Must Read)
- MODULE_REQUIREMENTS_scanner.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (Watchlist & Focus items 7–9, print contract items 22–24)
- EPOCH_05_GOVERNANCE.md

## Allowed Files (Strict)
- src/scanner/universe.py
- src/scanner/scoring.py
- src/scanner/scanner_runner.py
- src/scanner/print_contract.py
- src/utils/validation.py (only for schema checks)
- src/utils/logging.py (only for printing helpers)

## Tasks
1. Implement hard gates (explicit drop reasons):
   - price bounds
   - % change threshold
   - RVOL threshold
   - liquidity/spread threshold
   - optional float bounds / volume bounds (if already present in requirements)
2. Produce:
   - Watchlist K (post-gates, ranked)
   - Focus M (top subset from K)
3. Track state across cycles:
   - NEW / CONTINUING / DROPPED
4. Print a drop reason histogram/summary per cycle.

## Commands (Mandatory)
From repo root:
1. `python -m src.scanner.scanner_runner --mode READONLY --cycles 1`

## Required Console Output
- `TopN: <n>`
- `GatedSurvivors: <s>`
- `DropReasons: ...` (summary histogram)
- `WatchlistK: [SYM, ...]`
- `FocusM: [SYM, ...]`
- If empty: `EMPTY WATCHLIST (valid)` + reason summary

## Acceptance Checklist
- Output is stable and unambiguous.
- Empty output is treated as valid, not failure.
- Downstream modules can consume structured scanner artifact (not only prints).

## Rollback Rule
Avoid changing the scan source or adding new data providers here; focus on contract and clarity.

END.
