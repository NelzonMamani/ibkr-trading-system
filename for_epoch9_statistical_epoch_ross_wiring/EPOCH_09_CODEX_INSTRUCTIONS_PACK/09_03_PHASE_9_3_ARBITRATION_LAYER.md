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


## Phase 9.3 Objective
Implement deterministic arbitration rules to prevent strategies from competing on the same symbol.

No live wiring. This module must operate purely on provided inputs.

## Allowed Files
- `src/strategy_portfolio/arbitration.py`
- `src/strategy_portfolio/reason_codes.py`
- tests under `tests/strategy_portfolio/`

## Arbitration Model (Authoritative for Epoch 9)
- Rule: **One active strategy per symbol** at a time.
- Inputs:
  - a list of candidate intents per symbol, each tied to a strategy_id and priority
- Output:
  - winning intent (or NO_TRADE) + loser dispositions (DENIED or EXIT_ONLY)

## Implementation Steps
1. Create `src/strategy_portfolio/arbitration.py`
   - Define `ArbitrationInput`:
     - symbol
     - strategy_id
     - priority
     - proposed_intent (SignalIntent)
   - Define `ArbitrationResult`:
     - symbol
     - winner_strategy_id (or None)
     - winner_intent (SignalIntent)
     - denied: list[tuple[str, str]]  # (strategy_id, reason_code)
     - exit_only: list[tuple[str, str]]
   - Implement `arbitrate_symbol(inputs_for_symbol)`:
     - Filter to intents that are not NO_TRADE.
     - Choose highest priority; tie-breaker: strategy_id lexicographically.
     - Deny others with reason code `ARBITRATION_DENY_LOWER_PRIORITY`.
     - If a loser proposed ENTER, mark as DENIED.
     - If a loser is already in position (not known here), that would be EXIT_ONLY; for now, expose a parameter `loser_has_position: bool` or accept optional flag map.
   - Implement `arbitrate_all(inputs: list[ArbitrationInput])` grouping by symbol.

2. Add tests `tests/strategy_portfolio/test_arbitration.py`
   - Multiple strategies same symbol -> deterministic winner.
   - Tie-breaking works.
   - NO_TRADE excluded from competition.
   - Losers correctly assigned reason codes.

## Mandatory Verification Commands
- `python -m compileall -q src`
- `python -m pytest -q`
