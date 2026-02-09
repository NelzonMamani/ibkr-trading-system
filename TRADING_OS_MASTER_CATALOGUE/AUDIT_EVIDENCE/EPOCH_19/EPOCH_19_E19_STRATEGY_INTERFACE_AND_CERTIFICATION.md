# EPOCH 19 — Strategy Interface & Certification (E19)

## Summary
E19 formalizes strategy contracts, execution profiles, and contract validation to ensure strategies declare deterministic interfaces suitable for arbitration and certification.

## Scope
- `src/strategies/strategy_contracts.py`
- `src/strategies/strategy_base.py`
- `src/strategies/strategy_registry.py`
- `tests/test_strategy_registry_epoch13.py`
- `tests/test_ross_strategy_registry.py`

## Evidence
Command outputs are captured in this folder:
- `python -m compileall src tests` → `compileall.txt`
- `pytest tests/strategy_portfolio tests/strategies tests/test_ross_strategy_registry.py tests/test_strategy_registry_epoch13.py tests/smoke` → `pytest.txt`

## Notes
- Contracts validate against the E18/E20 foundation catalogue to prevent unknown primitives.
