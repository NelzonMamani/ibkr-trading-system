# 10_90_MANDATORY_VERIFICATION_COMMANDS.md — MANDATORY VERIFICATION (AUTHORITATIVE)

Codex MUST run these after each phase and fix until green.

From repo root (PowerShell or bash equivalents acceptable):

1) Compile
- `python -m compileall src`

2) Unit tests
- `pytest -q`

3) Strategy import smoke
- `python -c "import src.strategies.long_horizon_value as _; print('OK')"`
  (If package path differs, discover correct import by searching existing strategies.)

4) Strategy wiring smoke (SIM)
- Run 1 cycle in SIM mode using the existing CLI style:
  - Example pattern seen in repo: `python -m src.main --mode SIM --cycles 1 --strategy <name>`
  - Codex MUST discover the correct flag names and strategy key from `strategy_registry.py`.
  - Run with `--strategy long_horizon_value` (or the registered key) once wired.

5) Paper harness (once Phase 08 exists)
- Run 1–3 cycles in PAPER mode:
  - `python -m src.main --mode PAPER --cycles 1 --strategy long_horizon_value`
- Confirm no execution leakage and that intents/reports are produced.

Logging artifacts:
- Save logs under `output/verification/` consistent with repo conventions.

If any command fails:
- Fix code
- Re-run the entire verification list

END
