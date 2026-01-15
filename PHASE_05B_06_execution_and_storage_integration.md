# PHASE_05B_06_execution_and_storage_integration

Date: 2026-01-15

## Objective
Integrate Execution and Storage safely:
- Execution submits broker orders only when risk-approved and only in LIVE_1SHARE mode.
- Storage persists every attempt with full context (including blocked/failed).

## Inputs (Must Read)
- MODULE_REQUIREMENTS_execution.md
- MODULE_REQUIREMENTS_storage.md
- EPOCH_05_GOVERNANCE.md (mode law; storage mandatory)

## Allowed Files (Strict)
Execution:
- src/execution/order_router.py
- src/execution/order_tracker.py
- src/execution/exits.py

Storage:
- src/storage/trade_store.py
- src/storage/schema_map.py
- src/storage/review_queries.py

Integration (minimal):
- src/core_engine/orchestrator.py (only for wiring calls)
- src/utils/logging.py

## Tasks
1. Enforce mode law in execution:
   - READONLY: never submit; log “would place”
   - SIM: never submit
   - LIVE_1SHARE: submit only if risk-approved and sized within constraints
2. Track order lifecycle:
   - submitted, partial, filled, cancelled, rejected
3. Persist storage records for:
   - blocked trades
   - failed execution attempts
   - executed trades + fills
   Record must link: scanner artifact → pattern results → trade intent → risk decision → execution events → health snapshot.

## Commands (Mandatory)
From repo root:
1. `python -m src.core_engine.orchestrator --mode READONLY --cycles 1`
2. `python -m src.core_engine.orchestrator --mode SIM --cycles 2`

## Required Console Output
- Execution summary line (READONLY shows “would place”, never “submitted”)
- Storage confirmation line (success/failure)
- If storage fails: explicit error + safe degradation

## Acceptance Checklist
- No broker submissions in READONLY/SIM.
- Storage persists blocked attempts and successful attempts.
- Orchestrator completes cycle with clear output.

## Rollback Rule
If broker wiring introduces instability, keep a stubbed execution layer for READONLY/SIM while retaining full logs and storage.

END.
