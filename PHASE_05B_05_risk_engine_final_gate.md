# PHASE_05B_05_risk_engine_final_gate

Date: 2026-01-15

## Objective
Implement the Risk Engine as the final authority that gates TradeIntents.
It must enforce sizing, thresholds, and circuit breakers with explicit rationale for every decision.

## Inputs (Must Read)
- MODULE_REQUIREMENTS_risk.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (risk items 18–21)
- EPOCH_05_GOVERNANCE.md

## Allowed Files (Strict)
- src/risk/position_sizing.py
- src/risk/limits.py
- src/risk/risk_audit.py
- src/risk/risk_engine.py (or equivalent central module)
- src/utils/logging.py
- src/utils/validation.py

## Tasks
1. Implement RiskDecision contract:
   - ALLOW / BLOCK / ALLOW_WITH_CONSTRAINTS
   - max_position_size_allowed
   - rationale text and flags
2. Enforce Phase 1 defaults:
   - LIVE_1SHARE supported
   - capped testing risk budget
   - daily loss limit, max trades, data quality blocks, spread blocks
3. Ensure risk decisions are logged in a “teacher style”:
   - rule evaluated
   - threshold
   - action taken
   - why

## Commands (Mandatory)
From repo root:
1. `python -m src.risk.risk_engine --mode SIM --sample_intent` (or equivalent harness)

## Required Console Output
- Decision line: `RISK <ALLOW/BLOCK/...> size=<n> reason=<...>`
- If blocked: shows which rule triggered

## Acceptance Checklist
- Risk engine runs standalone.
- Risk engine never places orders.
- Decisions are deterministic for identical inputs.

## Rollback Rule
Do not add complex trailing-stop logic here; keep Phase 1 core risk gates first.

END.
