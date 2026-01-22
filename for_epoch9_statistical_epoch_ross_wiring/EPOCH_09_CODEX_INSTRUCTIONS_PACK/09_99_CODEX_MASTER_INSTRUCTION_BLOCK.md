# Epoch 9 — Strategy Portfolio Governance (Codex Implementation Instructions)
Date: 2026-01-22

## Non‑Negotiable Constraints (Global)
1. DO NOT modify any files under:
   - `src/strategies/ross_momentum/**`
   - any file named `strategy_policy.py` inside `ross_momentum`
2. DO NOT modify the existing orchestrator behaviour or flow yet.
   - No edits to `src/core/orchestrator.py` (or equivalent orchestrator module) in this epoch.
3. This epoch is **infrastructure-only**:
   - Add new modules/classes/tests that will later be wired in.
   - Ensure they are importable and testable in isolation.
4. No changes to scanner logic, execution logic, or risk engine logic.
5. All new code must be additive and safe to ignore until wired later.

## Mandatory Verification Commands (Must Pass)
Run these commands at the end of each phase (and fix any failures immediately):
1. `python -m compileall -q src`
2. `python -m pytest -q`
If the repo contains additional mandatory checks already used in CI (e.g., ruff/mypy), run them too,
but do not introduce new tooling requirements in this epoch.


## Codex Master Instruction Block (Copy/Paste)
You are implementing **Epoch 9 — Strategy Portfolio Governance** as additive infrastructure.

### Read First
1. Read `09_00_EPOCH_09_EXECUTION_ORDER.md` and follow the phase order.
2. For each phase document `09_01` .. `09_07`:
   - Implement exactly what is specified.
   - Do not introduce extra features.
   - Run the Mandatory Verification Commands after each phase.
   - If any command fails, fix it immediately before proceeding.

### Absolute Constraints
- Do not modify Ross strategy files (`src/strategies/ross_momentum/**`).
- Do not modify orchestrator files yet.
- Do not modify scanner, execution, or risk engine logic.

### Deliverables
- New package `src/strategy_portfolio/` with:
  - contracts, registry, arbitration, allocation, normaliser, reason_codes
- New tests under `tests/strategy_portfolio/`
- All tests passing.

### Final Output
When finished, provide:
- a summary of files added/changed (paths only)
- proof of Mandatory Verification Commands passing (command output excerpts)
