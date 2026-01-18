# A9 — Live readiness gate (preflight + arming)

## Intent
Make LIVE trading a deliberate, auditable action with pre-flight checks and explicit arming.

## Scope
Doctor checks + configuration + operator checklist.

## Required Outputs (Files / Modules)
- `src/core_engine/doctor.py`
- `docs/LIVE_READINESS_CHECKLIST_ROSS.md`

## Implementation Steps (Codex must follow exactly)
1. Add preflight checks: market data, time authority, IBKR connectivity, account type, kill-switch, risk limits, session phase sanity.
2. Implement `LIVE_ARM` flag required for LIVE submissions (in config/env). Default false.
3. Write operator checklist for UK operator: show NY session times alongside UK times; emphasize DST mismatch dates.
4. Any preflight failure blocks submission and prints remediation.

## Definition of Done (DoD)
- Live mode cannot submit without LIVE_ARM and passing preflight.
- Checklist exists and matches system behaviour.
- All tests pass.

## Validation Commands
- `pytest -q`
