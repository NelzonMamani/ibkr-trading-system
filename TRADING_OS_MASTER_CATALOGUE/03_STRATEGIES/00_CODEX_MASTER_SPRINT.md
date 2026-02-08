# STRATEGIES P05–P20 — CODEX MASTER SPRINT INSTRUCTION (Single Block)
**Timestamp:** 2026-02-08T01:28:21Z

You will implement and certify ALL strategies P05 through P20 as complete modules under `src/strategies/`.

Non-negotiable:
- NO PARTIALS for each strategy.
- Each strategy must have a complete strategy_policy.py with all tunables and mapping tables.
- Each strategy must be wired via E19 strategy factory/registry.
- Each strategy must have strategy-local unit tests.
- E21 must be executed with all strategies (SIM + PAPER + READ_ONLY + LIVE-safety).

Execution order (strict):
P05 → P06 → P07 → ... → P20 (sequential; no parallel).

For each strategy:
1) Read its GOV/*.md files
2) Implement the full strategy module
3) Add tests
4) Run verification
5) Append results to a single root-level `PR_VERIFICATION_REPORT.md` (with per-strategy sections)
6) Only then proceed to next.

Stop only when all strategies pass certification checklist.

END
