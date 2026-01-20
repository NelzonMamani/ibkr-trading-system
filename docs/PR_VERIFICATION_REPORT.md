# PR Verification Report

## Stock Selection Authority
- Strategy owns stock selection: `StockSelectionSpec` lives in the Ross Momentum strategy policy and is returned to the orchestrator for scanner use.
- Scanner is policy-agnostic: gates derive from the provided spec and policy_from_config is only used for non-strategy runs.
- Orchestrator is pass-through: strategy stock selection policy is forwarded unchanged into scanner execution.

## Verification Commands
1. `python -m compileall -q src`
   - Result: Failed — `src/broker/broker_interface.py` contains non-Python diff text (pre-existing).
2. `pytest -q`
   - Result: Passed.
3. `python -m src.main --mode SIM --cycles 1`
   - Result: Passed.
4. `python -m src.main --mode PAPER --cycles 1`
   - Result: Passed.
5. `python -m src.main --mode LIVE_MICRO --cycles 1`
   - Result: Halted safely on deterministic feed as expected.
