# A5 — Exit engine mapping to Ross behaviours (partials, trailing, time/failure exits)

## Intent
Implement Ross-style trade management: partials, break-even moves, trailing logic, time/failure exits.

## Scope
Exit plan generation + integration with existing `trade_exit_engine` and order tracker.

## Required Outputs (Files / Modules)
- `src/execution/trade_exit_engine.py`
- `src/strategies/ross_momentum/strategy_policy.py`
- `src/strategies/ross_momentum/ross_momentum_risk_overlay.py`

## Implementation Steps (Codex must follow exactly)
1. Map Ross policy exit parameters into the exit engine: initial stop, partial targets, break-even move, trailing rules, and time-based exits when momentum fades.
2. Implement topping-tail behaviour: wick/body ratio on 1m triggers PAUSE new entries and tightens trailing; do not force exit unless hard-exit conditions are met.
3. Implement hard exits: failed breakout, loss of VWAP with heavy red volume, breakdown through key level, repeated HOD rejection with strong selling.
4. Unit test exit precedence ordering.

## Definition of Done (DoD)
- Exit engine actions are deterministic for a given context.
- Partials + trailing + hard exits covered by fixture tests.
- All tests pass.

## Validation Commands
- `pytest -q`
