# A10 — Live rollout (gradual scale) + manual verification

## Intent
Move from paper to live safely with gradual scaling and manual verification via IBKR activity.

## Scope
Operational procedure + configurable caps + shadow mode.

## Required Outputs (Files / Modules)
- `docs/LIVE_ROLLOUT_PLAN_ROSS.md`
- `src/config/trading_config.py (caps)`
- `src/risk/risk_engine.py (enforce caps)`

## Implementation Steps (Codex must follow exactly)
1. Implement live size caps (configurable): start 1 share; cap max symbols, max trades/day, max notional/day.
2. Add staged rollout flags: STAGE_0_SHADOW, STAGE_1_MICRO, STAGE_2_LIMITED, STAGE_3_SCALE; each requires a config change.
3. Document manual verification: operator checks IBKR Orders/Trades; mismatch triggers kill-switch and STOP_DAY latch.
4. Add 'shadow mode' option: run decisions but no submission; for LIVE observation.
5. Ensure all logs show NY+UK times so operator never relies on UK clock for session phase.

## Definition of Done (DoD)
- Rollout plan exists with explicit caps and operator steps.
- Shadow mode + staged caps implemented.
- All tests pass.

## Validation Commands
- `pytest -q`
