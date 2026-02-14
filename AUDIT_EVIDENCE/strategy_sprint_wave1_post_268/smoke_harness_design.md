# Strategy Smoke Harness Design (Post-268)

- Script: `tools/strategy_smoke_harness.py`
- Purpose: execute one deterministic orchestrator cycle per strategy/mode without IBKR.
- Determinism controls:
  - `SCANNER_DATA_SOURCE=MOCK`
  - `SESSION_PHASE_OVERRIDE=MORNING`
  - fixed `SELECTED_STRATEGY`
  - mode explicitly set to `SIM` or `PAPER`
- Verifies pipeline markers from orchestrator output:
  - `SCANNER` (`[TRACE] stage=UNIVERSE`)
  - `WATCHLIST_K` (`[WATCHLIST]`)
  - `FOCUS_M` (`[TRACE] stage=FOCUS`)
  - `STRATEGY_RUNNER` (`STRATEGY_RUNNER_RECEIVED`)
  - `INTENTS` (`[INTENT]` lines; can be zero intents)
  - `EXECUTION` (`[EXECUTION]` stage output)
- Emits compact JSON to:
  - `AUDIT_EVIDENCE/strategy_sprint_wave1_post_268/smoke_<strategy>_<mode>.json`
