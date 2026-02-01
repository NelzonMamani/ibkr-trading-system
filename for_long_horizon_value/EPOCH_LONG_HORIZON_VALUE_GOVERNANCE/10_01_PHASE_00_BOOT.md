# 10_01_PHASE_00_BOOT.md — PHASE 00: BOOT & CONTEXT

Target code location:
- Strategy module: `src/strategies/long_horizon_value/`
  - Current files exist: `strategy_policy.py`, `runner.py`, `contracts/*`, `cadence.py`, `config.py`, `README.md`

Goal:
- Make the Long Horizon Value strategy runnable in ALL modes without execution leakage.
- Ensure strategy is discoverable via existing strategy registry / runner wiring.

Codex tasks:
1) Locate strategy registry/wiring:
   - Search for how `ross_momentum` and `statistical_intraday_momentum` are registered.
   - Add `long_horizon_value` registration following existing pattern.
2) Ensure `runner.py` conforms to expected runner interface used by orchestrator.
3) Add minimal “phase pipeline” scaffolding inside the runner WITHOUT adding new folders yet.
   - Runner must return a dict with keys:
     - `trade_intents` (list)
     - `reports` (list)
     - `metrics` (dict)
4) Implement strict mode safety:
   - In LIVE_READ_ONLY and LIVE_MICRO (or any read-only safety mode), strategy must never request execution.
   - Runner must still produce reports and trade intents (non-executable) if allowed by mode.
5) Implement cadence gating:
   - Enforce `ALLOWED_RUN_WINDOWS` in `cadence.py` (weekend/after-hours).
   - If disallowed window → produce report stating “SKIPPED_BY_CADENCE” and return empty intents.

Do NOT:
- Modify `strategy_policy.py` thresholds/logic.
- Add market-data fetching yet.

Deliverables:
- Strategy is selectable via CLI (same style as others).
- A report artifact is emitted even when skipped.

Tests to add:
- `tests/strategies/long_horizon_value/test_policy_imports.py` (or similar pattern) ensuring imports succeed.
- Smoke test verifying runner returns expected output keys.

END
