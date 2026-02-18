# 99 — CODEX MASTER INSTRUCTION BLOCK (PHASE 2)

FILE: PHASE_2_STRATEGY_PATCH_AND_COMPLETION/99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: PHASE 2 — Strategy Patch & Completion (Institutional Matrix V2)
DATE: 2026-02-18T21:00:41Z

You are Codex operating on repository: `ibkr-trading-system`.

GOAL
- Reconstruct strategies P02–P20 so each `StrategyPolicyV2` is institutionally complete.
- Matrix V2 audit must yield **CERTIFIED** for all P01–P20.
- Do NOT weaken the audit engine. Fix strategies.

CONSTRAINTS
- Prefer additive, strategy-local changes.
- No broad runtime refactors unless required for tests.
- Preserve P01 non-regression (must remain CERTIFIED).
- Respect canonical run modes: SIM, PAPER, READ_ONLY, LIVE.

WORK ITEMS (MANDATORY)
For each strategy P02–P20, edit:
- `src/strategies/<slug>/strategy_policy_v2.py`

Implement policy content to satisfy D0–D14:
- setup_families (>=1)
- trigger_model.entries (>=1)
- trigger_model.confirmations (>=1)
- exit_model.rules (>=1)
- intrabar doctrine:
  - APPLICABLE: phase_specs+timeframe_map
  - OR NOT_APPLICABLE with token INTRABAR and rationale
- liquidity_sanity_model.halt_policy explicit
- ranking rationale OR NOT_APPLICABLE token RANK
- data_requirements.required_fields includes: symbol, last_price, and pct_change|volume|rvol
- data requirements notes include pause/reject behaviour
- explicit safety escalation path
- session_reference_law non-empty (pct_change_reference or gap_reference)

MANDATORY VERIFICATION COMMANDS
Run from repo root:

```bash
python -m compileall src
pytest -q
```

SUCCESS CRITERIA
- `pytest -q` passes.
- Matrix V2 shows P01–P20 Verdict = CERTIFIED with domains PASS / legitimate NOT_APPLICABLE.
- Certification report shows Missing controls: None for all strategies.

STOP RULE
Stop immediately after success criteria are met and report:
- files changed
- commands executed
- final matrix summary

END
