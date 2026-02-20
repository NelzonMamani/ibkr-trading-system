# 04 — Mandatory Verification Commands

Run and record results (exit code + summary) in E26 evidence report:

1. `python -m compileall src`
2. `pytest -q`
3. `python -m src.core_engine.orchestrator --help`
4. Clean-room verification (tmp dirs):
   - `python -m src.runtime.regen snapshot-registry`
   - `python -m src.runtime.regen purge --level HARD --confirm`
   - `python -m src.runtime.regen bootstrap`
5. Orchestrator single-cycle determinism:
   - `python -m src.core_engine.orchestrator --mode READ_ONLY --cycles 1`

Notes:
- IBKR connectivity is not required for certification; safe degraded mode is acceptable.
- Tests must not touch real `data/ibkr_system.db` on the operator machine.
