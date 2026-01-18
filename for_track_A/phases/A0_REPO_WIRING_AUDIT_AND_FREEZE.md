# A0 — Repo wiring audit & invariants freeze

## Intent
Ensure Codex starts from the correct authoritative locations and does not accidentally modify legacy paths. Freeze invariants.

## Scope
No behavioural changes. Only imports, registry wiring, and doc clarification.

## Required Outputs (Files / Modules)
- `SYSTEM_STATE.md`
- `src/strategies/strategy_registry.py`
- `src/strategy/* (do not edit unless explicitly required)`

## Implementation Steps (Codex must follow exactly)
1. Confirm `src/strategies/ross_momentum/` contains `strategy.py`, `strategy_policy.py`, `strategy_context_schema.py`, and `TRADE_PERMISSION_MATRIX.md`.
2. Audit for duplicate/legacy Ross implementations under `src/strategy/` and ensure the orchestrator uses `src/strategies` plugin registry for Ross.
3. Update `src/strategies/strategy_registry.py` to register `RossMomentumStrategy` under a stable key (e.g., `ROSS_MOMENTUM`). Ensure only one canonical class is used.
4. Append a short note to `SYSTEM_STATE.md` and/or `EPOCH_05_GOVERNANCE.md` stating Track A uses `src/strategies/*` as authoritative and `src/strategy/*` is deprecated.
5. Run full test suite and ensure no diffs outside the intended wiring files.

## Definition of Done (DoD)
- Ross strategy is discoverable via `StrategyRegistry` and importable without side effects.
- No new runtime code paths reference `src/strategy/` for Ross (except optional compatibility wrappers).
- All tests pass.

## Validation Commands
- `pytest -q`
