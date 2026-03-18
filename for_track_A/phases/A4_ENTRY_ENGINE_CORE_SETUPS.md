# A4 — Entry engine — core Ross setups (Gap&Go, first pullback, micro pullback)

## Intent
Implement Ross entries as policy decisions producing TradeIntents, respecting permission matrix and session phase.

## Scope
Entries only; exits remain conservative (safety stops only) until A5.

## Required Outputs (Files / Modules)
- `src/strategies/ross_momentum/patterns/momentum_patterns.py`
- `src/strategies/ross_momentum/decision_policy.py`
- `src/strategies/ross_momentum/strategy.py`

## Implementation Steps (Codex must follow exactly)
1. Implement evaluators for: Gap & Go (break PMH/HOD), Opening Range Break (1m ORB), First Pullback Continuation, Micro Pullback re-entry trigger.
2. Micro pullback trigger must use: 2–3 red candles, weak selling (low volume vs impulse), and entry = first green candle that breaks above the last pullback candle high on 10s.
3. Wire evaluators into `decision_policy.py` with explicit reason codes and recorded evidence.
4. Convert policy decisions into `TradeIntent` with entry reference (break level), protective stop suggestion placeholder, and confidence score.
5. Add unit tests for each setup with fixtures to validate triggers and non-triggers.

## Definition of Done (DoD)
- All core entry setups generate TradeIntents deterministically in SIM from fixtures.
- No entry emitted when topping-tail pause flags active or permission matrix blocks.
- All tests pass.

## Validation Commands
- `pytest -q`
