# PHASE_05C_04_smoke_and_contract_tests

Date: 2026-01-15

## Objective
Add a minimal but effective test suite to prevent regressions and catch “Codex drift” immediately:
- import smoke tests
- scanner print/return contract tests (required fields)
- orchestrator readonly single-cycle test

## Inputs (Must Read)
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (standalone + integrated)
- EPOCH_05_GOVERNANCE.md (console proof + determinism)

## Allowed Files (Strict)
- tests/smoke/test_imports.py
- tests/smoke/test_scanner_contract.py
- tests/smoke/test_orchestrator_cycle.py
- (Optional) minimal test helpers under tests/helpers/

## Tasks
1. Add import smoke test for the canonical package root.
2. Add scanner contract test:
   - verifies required fields exist in returned artifact
   - does not require market open; should handle empty valid output
3. Add orchestrator readonly test:
   - one cycle completes without exceptions
   - no broker order submission functions are called in READONLY

## Commands (Mandatory)
From repo root:
1. `python -m pytest -q`

## Acceptance Checklist
- All tests pass.
- Tests are fast and deterministic.
- Scanner contract test passes even when watchlist is empty (valid).

END.
