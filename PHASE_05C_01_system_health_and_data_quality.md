# PHASE_05C_01_system_health_and_data_quality

Date: 2026-01-15

## Objective
Implement robust health and data quality handling:
- OK / DEGRADED / CRITICAL health states
- Safe-stop on CRITICAL conditions
- Clear logging of data-quality flags

## Inputs (Must Read)
- MODULE_REQUIREMENTS_core_engine.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (data reliability and fallback items 25–27; recovery items 31–32)
- EPOCH_05_GOVERNANCE.md

## Allowed Files (Strict)
- src/core_engine/health.py
- src/core_engine/state.py
- src/utils/validation.py
- src/utils/logging.py

## Tasks
1. Define health states and triggers:
   - broker disconnected
   - stale/missing data
   - storage failure (if non-recoverable)
2. Ensure orchestrator behavior on CRITICAL:
   - stop trading actions
   - continue logging and safe shutdown/recovery steps
3. Print health status each cycle with trigger reasons.

## Commands (Mandatory)
From repo root:
1. `python -m src.core_engine.orchestrator --mode READONLY --cycles 2`

## Acceptance Checklist
- Health line prints OK/DEGRADED/CRITICAL.
- CRITICAL prevents execution actions.
- Triggers are explicit and actionable.

END.
