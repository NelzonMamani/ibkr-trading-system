# PHASE_05B_01_orchestrator_deterministic_cycle

Date: 2026-01-15

## Objective
Implement a deterministic, non-overlapping orchestrator cycle that executes modules in the frozen order:
Scanner → Data hydrate → Patterns → Strategy → Risk → Execution → Storage → Health summary.

## Inputs (Must Read)
- MODULE_REQUIREMENTS_core_engine.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (items 33–34; standalone + integrated)
- EPOCH_05_GOVERNANCE.md (cycle determinism, mode law)

## Allowed Files (Strict)
- src/core_engine/orchestrator.py
- src/core_engine/state.py
- src/core_engine/health.py
- src/core_engine/events.py
- src/utils/time_utils.py
- src/utils/logging.py

## Tasks
1. Ensure deterministic order and prevent overlapping cycles.
2. Print a cycle header:
   - cycle id
   - mode
   - session (PRE/REG/AFTER)
3. Ensure orchestrator handles empty scanner outputs gracefully:
   - no crash
   - skip downstream modules if FocusM empty (but still prints state)
4. Produce a CycleSummary at end of each cycle.

## Commands (Mandatory)
From repo root:
1. `python -m src.core_engine.orchestrator --mode READONLY --cycles 1`

## Required Console Output
- `CYCLE <n> MODE=<...> SESSION=<...>`
- `Scanner: TopN=<n> Survivors=<s> K=<k> M=<m>`
- End-of-cycle summary includes health status (OK/DEGRADED/CRITICAL).

## Acceptance Checklist
- One cycle completes deterministically.
- No overlaps (no concurrent cycle logs).
- Empty FocusM does not crash the loop.

## Rollback Rule
Do not introduce event-driven refactors; keep the cycle model simple and conservative.

END.
