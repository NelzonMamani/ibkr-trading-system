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


## Phase 9.2 Objective
Implement a Strategy Registry that can:
- Register strategies (metadata only)
- Enable/disable them
- Assign priorities
- Provide deterministic ordering

This registry is **not yet wired** to orchestrator execution.

## Allowed Files (This Phase)
- `src/strategy_portfolio/registry.py`
- `src/strategy_portfolio/contracts.py` (only if required to add small types)
- tests under `tests/strategy_portfolio/`

## Implementation Steps
1. Create `src/strategy_portfolio/registry.py`
   - Define `StrategyState`: REGISTERED, ENABLED, DISABLED, DEPRECATED
   - Define `StrategyRegistryEntry` dataclass:
     - identity
     - state
     - priority (int; higher wins)
     - supported_modes (dict[str,bool]) (optional)
     - description (optional)
     - policy_provider (callable or import path string) — **do not execute**, store reference only
   - Define `StrategyRegistry` class:
     - `register(entry)` (idempotent)
     - `enable(strategy_id)` / `disable(strategy_id)`
     - `set_priority(strategy_id, priority)`
     - `list_enabled_ordered()` returns enabled entries sorted by priority desc then strategy_id asc
     - `get(strategy_id)`
   - Design decisions:
     - Deterministic ordering required.
     - Default state should be DISABLED unless explicitly enabled (fail-safe).
     - Missing entry -> raise a clear exception.

2. Add tests `tests/strategy_portfolio/test_registry.py`
   - Register multiple entries and verify deterministic sort.
   - Verify enable/disable toggles.
   - Verify default DISABLED.
   - Verify idempotent register does not duplicate.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
