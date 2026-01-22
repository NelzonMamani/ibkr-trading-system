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


## Phase 9.4 Objective
Implement a capital allocation governance module that computes per-strategy budgets and denies new risk when exhausted.

This is policy-level accounting only; it must not place orders or interact with broker APIs.

## Allowed Files
- `src/strategy_portfolio/allocation.py`
- tests under `tests/strategy_portfolio/`

## Allocation Model (Minimal, Deterministic, Extensible)
- Inputs:
  - account_equity (float)
  - global_max_risk_pct (float) OR global_max_risk_usd (float)
  - per-strategy allocation config: fixed_pct / capped_pct / disabled (0)
- Outputs:
  - per-strategy risk_budget_usd
  - remaining_budget_usd after reservations (optional)

## Implementation Steps
1. Create `src/strategy_portfolio/allocation.py`
   - Define `AllocationConfig` dataclass:
     - strategy_id
     - allocation_pct (0..1)  # share of global risk budget
     - max_allocation_usd (optional cap)
     - enabled (bool)
   - Define `AllocationResult` dataclass:
     - strategy_id
     - enabled
     - budget_usd
     - reason_codes (list[str])
   - Implement `compute_global_risk_budget(account_equity, global_max_risk_pct=None, global_max_risk_usd=None)`
     - Must require at least one of pct/usd.
     - Deterministic output.
   - Implement `allocate(global_budget_usd, configs)`:
     - Disabled -> budget 0 + reason `ALLOCATION_DISABLED`
     - For enabled strategies: budget = global_budget_usd * allocation_pct, then apply cap if present
     - Ensure no negative budgets.
   - Optional: implement a simple `reserve_budget(strategy_id, amount)` in a stateful allocator class (but keep minimal; may be deferred).

2. Add tests `tests/strategy_portfolio/test_allocation.py`
   - pct-based allocation sums behave as expected.
   - caps applied.
   - disabled yields 0 + reason.
   - invalid inputs raise clear errors.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
