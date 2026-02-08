# P02 — CODEX INSTRUCTIONS — 05_MANDATORY_VERIFICATION
You MUST run and record outputs for:
- `python -m compileall src`
- `pytest -q`
- Strategy-local tests path: `src/strategies/statistical_intraday_momentum/tests`
- E21 run (SIM): scan→watchlist→focus→intents
- E21 run (PAPER): intents→paper execution provider→DB writes
- READ_ONLY run: intents emitted, no orders submitted

If any step fails:
- Fix additively.
- Re-run verification.
- Do not claim completion until all are green.

END
