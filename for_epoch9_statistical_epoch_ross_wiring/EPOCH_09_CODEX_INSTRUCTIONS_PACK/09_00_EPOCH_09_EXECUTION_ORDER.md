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


## Purpose of This File
This document is the single authoritative order-of-operations for implementing Epoch 9.
Codex must execute phases strictly in order, passing the Mandatory Verification Commands after each phase.

## Phase Order
- Phase 9.1 — Interface Contract (Python contract + schemas; no wiring)
- Phase 9.2 — Strategy Registry (enable/disable + priorities; no wiring)
- Phase 9.3 — Arbitration Layer (conflict resolution rules; no wiring)
- Phase 9.4 — Capital Allocation Governance (budgets/caps; no wiring)
- Phase 9.5 — Orchestrator Normaliser (standalone adapter functions; no orchestrator edits)
- Phase 9.6 — Non‑Interference Guardrails (explicit “do not touch” asserts + docs)
- Phase 9.7 — Validation Suite (tests proving no imports break, determinism, and safe defaults)

## New Package Layout (Create if missing)
Create a new package to host the governance layer. Suggested:
- `src/strategy_portfolio/`
  - `__init__.py`
  - `contracts.py`
  - `registry.py`
  - `arbitration.py`
  - `allocation.py`
  - `normaliser.py`
  - `reason_codes.py`
  - `schemas.py` (if needed; keep minimal)
- `tests/strategy_portfolio/` (new tests, isolated)

## Acceptance Criteria (Epoch 9 Definition of Done)
- New modules exist and are importable without touching orchestrator.
- Safe defaults enforce **DISALLOW/NO_TRADE** when fields are missing.
- Registry supports enable/disable and priority ordering.
- Arbitration resolves conflicts deterministically.
- Allocation computes per-strategy budgets deterministically.
- Normaliser can translate a strategy policy object into canonical intents without executing trades.
- All Mandatory Verification Commands pass.
