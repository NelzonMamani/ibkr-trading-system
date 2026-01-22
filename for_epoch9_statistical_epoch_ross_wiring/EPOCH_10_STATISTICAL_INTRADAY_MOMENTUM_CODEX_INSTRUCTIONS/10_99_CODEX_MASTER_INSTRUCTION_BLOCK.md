# Epoch 10 — Statistical Intraday Momentum (Codex Implementation Instructions)
Date: 2026-01-22

## Global Constraints (Non-Negotiable)
1. DO NOT modify any files under:
   - `src/strategies/ross_momentum/**`
2. DO NOT modify orchestrator flow yet:
   - No edits to `src/core/orchestrator.py` (or equivalent orchestrator module) in this epoch.
3. DO NOT modify scanner logic, execution logic, or global risk engine logic.
4. This epoch must be **additive**:
   - Only add the new strategy module and its tests.
   - Strategy must compile and be testable in isolation.
5. Strategy must be **interface-native**:
   - It must use the Epoch 9 governance types in `src/strategy_portfolio/*` (contracts, reason codes, etc.)
6. Strategy must not require new third-party dependencies.
7. Provide comments in all policy/config sections explaining intent and safe defaults.

## Mandatory Verification Commands (Must Pass)
Run at the end of each phase (and fix failures immediately):
1. `python -m compileall -q src`
2. `python -m pytest -q`

If repo already has existing required checks (ruff/mypy), run them too,
but do not add new tool requirements in this epoch.


## Codex Master Instruction Block (Copy/Paste)
Implement **Epoch 10 — Statistical Intraday Momentum** as a new isolated strategy module.

### Execute in Order
1. Read `10_00_EPOCH_10_EXECUTION_ORDER.md`.
2. Implement `10_01` .. `10_06` in order.
3. After each phase run:
   - `python -m compileall -q src`
   - `python -m pytest -q`
   Fix failures immediately before proceeding.

### Constraints
- Do not modify `src/strategies/ross_momentum/**`.
- Do not modify orchestrator, scanner, execution, or global risk engine logic.
- Do not add new dependencies.

### Required Output
At completion:
- list all files added/changed (paths only)
- paste verification command outputs (or key excerpts)
