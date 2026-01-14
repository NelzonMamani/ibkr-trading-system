# PHASE_30_STRATEGY_EXPLAINABILITY_AND_LOGS

## Objective
Standardise **human-readable explainability** for strategy decisions so that every decision can be audited quickly.

## Scope
### In-Scope
- Logging conventions:
  - per-symbol evaluation header
  - pattern detection summary (counts, best setup)
  - intent emission summary (entry/stop/invalidations)
- Structured output conventions for downstream modules
- A minimal “decision trace” object that can later be stored in Storage (Epoch 4)

### Out-of-Scope
- Storage implementation (Epoch 4)
- Live-trade telemetry

## Files to Create/Modify (Repo)
- Create: `src/utils/teacher_logs.py` (if not already present)
- Modify: `src/strategies/ross_momentum/strategy.py` (apply log standards)
- Modify: `src/strategies/early_entry_momentum/strategy.py` (apply log standards)

## Definition of Done
- Running a strategy prints:
  - a clear reason for each detected/rejected pattern
  - a clear reason why an intent was or was not emitted
  - all outputs are deterministic for identical inputs
