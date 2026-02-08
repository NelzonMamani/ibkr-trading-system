# P03 — CODEX INSTRUCTIONS — 04_IMPLEMENTATION_TASKS
1) Reality check: locate existing P03 strategy folder and current policy/runner.
2) Align to governance docs:
   - Implement complete canon mapping in P03 policy: SF/XL/C/K/SCP/MCP/LVL/ZONES/INV.
   - Ensure all tunable thresholds live in policy.
3) Ensure strategy emits intents with full traceability fields (SF/XL/C/K/INV).
4) Add strategy-local tests:
   - Pure policy tests (no orchestrator/broker/DB)
   - Deterministic trace fields test
   - Edge-case tests for opening mode restrictions and regime veto
5) Ensure E21 harness runs P03 in SIM and PAPER with deterministic outputs.
6) Produce PR_VERIFICATION_REPORT.md with commands and results.

END
