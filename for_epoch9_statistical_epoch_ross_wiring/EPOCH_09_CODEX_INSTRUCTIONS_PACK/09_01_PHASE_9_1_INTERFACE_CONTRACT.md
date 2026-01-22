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


## Phase 9.1 Objective
Implement the **Strategy Interface Contract** as Python types, reason codes, and a canonical intent vocabulary.
This must be usable by future strategies (Statistical Intraday Momentum) without modifying Ross.

## Files Allowed To Add/Modify (This Phase)
- Add new files under `src/strategy_portfolio/**`
- Add new tests under `tests/strategy_portfolio/**`
- You may add `__init__.py` files where needed.

## Files Explicitly Forbidden (This Phase)
- Any file under `src/strategies/ross_momentum/**`
- Orchestrator module(s) (do not touch)
- Scanner, execution, or risk modules

## Implementation Steps
1. Create `src/strategy_portfolio/reason_codes.py`
   - Define a structured set of reason codes (strings or Enum) for:
     - activation disallow
     - universe reject
     - data quality fail
     - arbitration deny
     - allocation exhausted
     - risk veto (placeholder)
     - missing field default
   - Keep it small but extensible.

2. Create `src/strategy_portfolio/contracts.py`
   - Define canonical enums/typed literals for:
     - `AllowState`: `ALLOW | DISALLOW`
     - `SignalIntent`: `ENTER_LONG | ENTER_SHORT | HOLD | EXIT_ONLY | NO_TRADE`
     - `OrderConstraint` (optional): allowable order styles (e.g., LIMIT, MARKETABLE_LIMIT) — just a vocabulary, no execution.
   - Define a minimal `StrategyIdentity` dataclass:
     - `strategy_id`, `strategy_version`, `strategy_family` (optional)
   - Define a minimal `StrategyPolicyContract` protocol (PEP 544) OR abstract base class:
     - Must expose identity + optional policy sections.
     - Do **not** enforce Ross to inherit; this is for new strategies.
   - Define `DecisionIntent` dataclass:
     - `allow_state`
     - `signal_intent`
     - `reasons: list[str]`
     - `metadata: dict` (optional)
   - Define `StrategyContextSnapshot` placeholder type (do not re-implement existing context; just a small interface the normaliser can accept).

3. Create `src/strategy_portfolio/schemas.py` (optional)
   - Only if you need small shared schemas for context/decision records.
   - Avoid duplicating existing project schemas.

4. Create tests `tests/strategy_portfolio/test_contracts.py`
   - Validate enums/literals values.
   - Validate defaults: if `DecisionIntent` created with empty reasons -> still valid.
   - Ensure modules import with no side effects.

## Mandatory Verification Commands
Run and fix:
- `python -m compileall -q src`
- `python -m pytest -q`
