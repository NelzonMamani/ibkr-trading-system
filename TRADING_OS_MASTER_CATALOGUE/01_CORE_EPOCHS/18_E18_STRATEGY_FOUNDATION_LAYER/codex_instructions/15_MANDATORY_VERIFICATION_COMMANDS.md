# E18 — MANDATORY VERIFICATION COMMANDS (RUN ALL, PASS ALL)

Codex must run and pass ALL of the following, in order.

A) Static checks
1. python -m compileall src

B) Unit tests
2. pytest -q

C) System reality verification (latest available)
3. python verification_scripts/verify_system_reality_v2.py  (or newest equivalent)

D) Foundation completeness proof
4. Run foundation registry completeness check (you must create/ensure):
   - proves all SF/XL/C/K and candle checklists are registered and implemented
   - fails if any checklist item is missing

E) Strategy mapping artifacts generation
5. Run report generator command (you must create/ensure) to generate:
   - STRATEGY_POLICY_TRANSLATION_REPORT.md per strategy
   - FOUNDATION_COVERAGE_CHECKLIST_<strategy_id>.md per strategy
   - DRIFT_AND_COMPATIBILITY_REPORT_<strategy_id>.md per strategy

F) Runtime smoke (non-live execution)
6. python -m src.main --mode SIM --cycles 1
7. python -m src.main --mode PAPER --cycles 1
8. python -m src.main --mode READ_ONLY --cycles 1
9. python -m src.main --mode LIVE --cycles 1   (execution disabled; verify gating)

All failures must be fixed before continuing.
Stop when all commands pass and E18 certification criteria are satisfied.

END
