# EPOCH 16 — No-Trade Contexts (E16)

## Summary
E16 formalizes explicit no-trade contexts and ensures they are evaluated deterministically before execution. A dedicated no-trade context evaluator consolidates session, execution, broker, circuit breaker, and data quality blocks into ordered, fail-safe gating.

## Scope
- `src/risk/no_trade_contexts.py`
- `src/risk/risk_engine.py`
- `src/models/risk_decision.py`
- `tests/test_epoch15_17_safety_cluster.py`

## No-Trade Context Coverage
- `evaluate_no_trade_contexts(...)` defines ordered hard blocks.
- Risk engine applies contexts early in both `evaluate_strategy_payload` and `evaluate_trade_intent`.
- Circuit breaker, READ_ONLY mode, execution-disabled, broker READ_ONLY, session block, and data-quality blocks are explicit.

## Required Tests
- No-trade context ordering: `tests/test_epoch15_17_safety_cluster.py::test_no_trade_contexts_order`.

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src` → `compileall.txt`
- `pytest tests/test_epoch15_17_safety_cluster.py` → `pytest.txt`

## Notes
- Context ordering is deterministic to prevent ambiguous or implicit execution decisions.
