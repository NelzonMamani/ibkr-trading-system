# A1 — Strategy integration contract (StrategyPolicy/StrategyContext/StrategyRunner)

## Intent
Make the contract explicit: Orchestrator builds StrategyContext based on StrategyPolicy requirements; StrategyRunner evaluates policy × context; outputs deterministic TradeIntents.

## Scope
Interfaces, dataclasses, and tests; minimal behaviour changes.

## Required Outputs (Files / Modules)
- `src/strategies/strategy_contracts.py`
- `src/strategies/strategy_base.py`
- `src/strategies/ross_momentum/strategy_policy.py`
- `src/strategies/ross_momentum/strategy_context_schema.py`
- `src/core/orchestrator.py or src/core_engine/orchestrator.py (whichever is canonical)`

## Implementation Steps (Codex must follow exactly)
1. Define/confirm `StrategyPolicy` interface: must expose `required_context()` (schema-like requirements) and `evaluate(context) -> PolicyDecision`.
2. Define/confirm `StrategyContext` dataclass (or typed dict) produced by orchestrator, including: timestamp, per-symbol snapshots, positions, active trades, session_phase, indicators, and optional L2 evidence.
3. Ensure Ross `strategy_policy.py` conforms to StrategyPolicy contract and explicitly declares required context fields (price/volume/VWAP/EMAs/MACD, relative volume, key levels).
4. Ensure `StrategyRunner` accepts `(policy, context)` and emits `TradeIntent` objects (existing intent model).
5. Add/extend unit tests verifying: (a) orchestrator can build minimal context; (b) policy blocks when required fields are missing, with explicit reason codes.

## Definition of Done (DoD)
- A strategy can be executed end-to-end in SIM without broker I/O by providing a StrategyContext fixture.
- Missing context fields produce a deterministic BLOCK decision with explicit reason codes.
- All tests pass.

## Validation Commands
- `pytest -q`
