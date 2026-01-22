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


## Phase 9.5 Objective
Implement an orchestrator **normaliser** as a standalone module that can translate:
- a strategy policy object (Ross-like or interface-native)
- a context snapshot (lightweight)
into canonical `DecisionIntent` outputs.

IMPORTANT: Do not modify the orchestrator yet.
This module is standalone and will be wired later.

## Allowed Files
- `src/strategy_portfolio/normaliser.py`
- `src/strategy_portfolio/contracts.py` (minimal additions only)
- tests under `tests/strategy_portfolio/`

## Normalisation Rules (Fail-Safe)
- If required policy fields are missing: return `DISALLOW` + `NO_TRADE`
- If context required fields missing: return `DISALLOW` + `NO_TRADE`
- Always emit explicit reason codes for defaults.

## Implementation Steps
1. Create `src/strategy_portfolio/normaliser.py`
   - Provide `normalise_strategy_policy(policy_obj) -> dict`
     - Extract identity fields if present (`name`/`strategy_id`, `version`/`strategy_version`).
     - Do not assume Ross inheritance; use attribute checks.
   - Provide `evaluate_activation(policy_obj, context) -> AllowState`
     - For Epoch 9, do NOT implement Ross logic. Only provide a placeholder mechanism:
       - If policy has `activation` section, evaluate basic booleans.
       - Otherwise DISALLOW (for non-wired strategies).
     - NOTE: This module is primarily for Statistical strategy later; Ross will be adapted in Step 3.
   - Provide `derive_decision_intent(policy_obj, context) -> DecisionIntent`
     - For Epoch 9, the function must be safe and conservative:
       - default DISALLOW/NO_TRADE unless the policy explicitly supports activation evaluation.
   - This phase’s goal is: **plumbing + safety defaults**, not trading intelligence.

2. Add tests `tests/strategy_portfolio/test_normaliser_defaults.py`
   - Empty policy object -> DISALLOW/NO_TRADE with reason `MISSING_POLICY_FIELDS`
   - Minimal interface-native policy dict -> can ALLOW if it explicitly contains an allow flag
   - Ensure no Ross modules imported

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
