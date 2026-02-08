# P03 — CODEX INSTRUCTIONS — 05_MANDATORY_VERIFICATION
Run and record:
- `python -m compileall src`
- `pytest -q`
- Strategy-local tests: `src/strategies/mean_reversion/tests`
- E21 SIM: scan→watchlist→focus→intents
- E21 PAPER: intents→paper execution provider→DB
- READ_ONLY: intents emitted, no orders
- LIVE safety check (execution authority respected)

END
