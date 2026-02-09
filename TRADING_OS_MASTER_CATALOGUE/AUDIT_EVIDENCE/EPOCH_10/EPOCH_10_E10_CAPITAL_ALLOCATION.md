# EPOCH 10 — Capital Allocation (E10)

## Certification Summary
E10 Capital Allocation is certified. Allocation logic is deterministic (stable ordering), risk-bounded (scaled to the global budget), and arbitration precedence remains deterministic with explicit priority ordering. The allocation path continues to rely on upstream risk budgets, ensuring no bypass of Risk Engine authority.

## Scope
- `src/strategy_portfolio/allocation.py`
- `src/strategy_portfolio/arbitration.py`
- `src/strategy_portfolio/contracts.py`
- `src/strategy_portfolio/registry.py`

## Evidence
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_10/compileall.txt`
- `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_10/pytest.txt`

## Tests Executed
- `python -m compileall src`
- `pytest`
