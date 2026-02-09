# EPOCH 20 — Strategy Foundation Completion (E20)

## Summary
E20 enumerates the canonical foundation primitives referenced by strategies (setup families, triggers, conditions, confirmations) and exposes compatibility checks for strategy contracts.

## Scope
- `src/strategies/common/foundation.py`
- `src/strategies/strategy_contracts.py`
- `tests/strategies/test_foundation_catalogue.py`

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src tests` → `compileall.txt`
- `pytest tests/strategy_portfolio tests/strategies tests/test_ross_strategy_registry.py tests/test_strategy_registry_epoch13.py tests/smoke` → `pytest.txt`
- `pytest` → `pytest_full.txt` (full-suite verification)

## Notes
- Foundation compatibility is versioned to support controlled evolution.
