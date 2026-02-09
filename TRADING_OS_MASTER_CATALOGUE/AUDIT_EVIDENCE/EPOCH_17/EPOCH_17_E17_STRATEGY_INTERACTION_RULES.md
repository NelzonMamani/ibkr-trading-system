# EPOCH 17 — Strategy Interaction Rules (E17)

## Summary
E17 hardens deterministic strategy arbitration by enforcing one intent per strategy per symbol, explicit budget gating, and consistent tie-breaking rules. Arbitration now prevents conflicting signals from a single strategy and blocks strategies with exhausted capital budgets.

## Scope
- `src/strategy_portfolio/arbitration.py`
- `src/strategy_portfolio/reason_codes.py`
- `tests/test_epoch15_17_safety_cluster.py`

## Strategy Interaction Coverage
- `_dedupe_inputs(...)` enforces deterministic per-strategy intent selection.
- `arbitrate_symbol(...)` includes budget gating via `strategy_budget_map` to prevent capital interference.
- `arbitrate_all(...)` forwards budget constraints across symbols.

## Required Tests
- Budget-gated arbitration: `tests/test_epoch15_17_safety_cluster.py::test_arbitration_budget_blocks_strategy`.

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src` → `compileall.txt`
- `pytest tests/test_epoch15_17_safety_cluster.py` → `pytest.txt`

## Notes
- Arbitration remains deterministic by priority + strategy id ordering, with explicit denial reasons for conflicts.
