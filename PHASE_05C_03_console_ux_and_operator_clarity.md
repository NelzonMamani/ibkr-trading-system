# PHASE_05C_03_console_ux_and_operator_clarity

Date: 2026-01-15

## Objective
Make console output operator-grade and unambiguous.
Specifically:
- Watchlist K symbols are always shown clearly
- Focus M symbols (top 3–5 by default) are always shown clearly
- Decisions (patterns, risk, execution, storage) are summarized clearly each cycle

## Inputs (Must Read)
- SYSTEM_STATE.md (console expectations)
- EPOCH_05_GOVERNANCE.md

## Allowed Files (Strict)
- src/utils/logging.py
- src/scanner/print_contract.py
- src/core_engine/orchestrator.py
- src/risk/risk_audit.py (only if needed for better rationale print formatting)

## Tasks
1. Standardize headers and summaries:
   - consistent section delimiters
   - stable ordering of sections
2. Ensure Focus M is printed as an explicit list (not buried).
3. Ensure execution summary and storage confirmation are always visible.

## Commands (Mandatory)
From repo root:
1. `python -m src.core_engine.orchestrator --mode READONLY --cycles 2`

## Acceptance Checklist
- A human can identify K and M in under 10 seconds from the console output.
- Risk decisions are readable and include “why”.
- READONLY never suggests an order was submitted; only “would place” language.

END.
