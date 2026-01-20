PHASE 3 — ORCHESTRATOR WIRING

Files:
src/core/orchestrator.py
src/core_engine/orchestrator.py

Actions:
- Orchestrator reads StrategyPolicy
- Calls stock_selection_policy_for_session_phase()
- Passes result into scanner unchanged
- Orchestrator may only adjust:
  - session phase
  - freshness timestamps
  - runtime safety (clock, price feed)

Forbidden:
- Tuning thresholds
- Overriding gates
