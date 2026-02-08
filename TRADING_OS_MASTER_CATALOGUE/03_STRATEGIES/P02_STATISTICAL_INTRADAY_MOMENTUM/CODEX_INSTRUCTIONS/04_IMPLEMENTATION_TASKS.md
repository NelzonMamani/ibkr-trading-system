# P02 — CODEX INSTRUCTIONS — 04_IMPLEMENTATION_TASKS
Execute in order:

1) Reality check: locate existing P02 strategy folder (if present) and current policy files.
2) Implement a canon-complete `strategy_policy.py` for P02 that includes:
   - StockSelectionSpec (tunables)
   - Mode/timeframe plan
   - ALLOWED/OPTIONAL/DENIED lists for SF/XL/C/K/SCP/MCP/LVL/ZONES/INV
   - Mapping tables (SF→XL, SF→required K, SF→optional K, SF→required levels, SF→invalidations)
3) Ensure strategy runner/orchestrator can consume the policy without breaking interface.
4) Add tests:
   - Unit tests for pure policy logic (no orchestrator/broker/DB)
   - A deterministic “decision trace” test that asserts SF/XL/C/K fields are present in intents
5) Add end-to-end verification script or update existing E21 harness to include P02 in SIM and PAPER.
6) Produce `PR_VERIFICATION_REPORT.md` summarising commands and outcomes.

Stop when:
- All checklist items in `GOVERNANCE/CERTIFICATION_CHECKLIST.md` are satisfied.

END
