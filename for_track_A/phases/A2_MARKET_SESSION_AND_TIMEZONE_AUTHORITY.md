# A2 — Market session & timezone authority (NY session, UK display)

## Intent
Eliminate DST ambiguity: compute US market session in America/New_York; render operator logs in Europe/London and UTC.

## Scope
Time utilities + session phase classification used by policy (open, mid, late, halt windows).

## Required Outputs (Files / Modules)
- `src/utils/time_utils.py`
- `src/strategies/ross_momentum/strategy_context_schema.py`
- `src/strategies/ross_momentum/strategy_policy.py`
- `src/core/orchestrator.py (context builder: session phase)`

## Implementation Steps (Codex must follow exactly)
1. Implement `market_session_phase(now_utc) -> SessionPhase` using `zoneinfo`. America/New_York is the session authority.
2. Define phases minimally: PREMARKET, OPENING_0_30, MORNING, MIDDAY, LATE, POWER_HOUR, CLOSED. Boundaries are NY-local times converted from UTC.
3. Add `session_phase`, `ny_time`, and `uk_time` to StrategyContext.
4. Update Ross policy to allow session_phase-specific parameter sets (morning fast microstructure vs late slower). Do not invent new rules—only parameterize timing.
5. Add tests validating DST transitions (US and UK differ): sample UTC timestamps map to correct NY phases and correct UK display times.

## Definition of Done (DoD)
- Session phase is correct across DST changes with unit tests.
- StrategyContext always includes NY and UK times for operator clarity.
- All tests pass.

## Validation Commands
- `pytest -q`
