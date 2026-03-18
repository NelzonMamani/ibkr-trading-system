# A8 — Paper trading harness + operator telemetry

## Intent
Run the full system against IBKR paper with clear logs, strategy reasons, and manual verification support.

## Scope
Integration, CLI, logging; no new strategy logic.

## Required Outputs (Files / Modules)
- `src/main.py`
- `src/cli/ (add Ross paper command)`
- `RUNBOOK.md (update: paper steps)`

## Implementation Steps (Codex must follow exactly)
1. Add a CLI/run entrypoint for Ross PAPER mode (config-driven ports).
2. Ensure no order submits unless `order_submission_enabled=true` and `paper_only_enforced=true`.
3. Log per-trade: setup name, key levels, entry trigger, stop, partial plan, trailing rule, permission matrix state.
4. Write a daily session report to `output/` with NY/UK/UTC times and a chronological timeline of events.
5. Smoke test when market is closed to ensure graceful behaviour (no crash).

## Definition of Done (DoD)
- Operator can run a paper session and see full decision reasons in logs.
- Orders are only paper and only when explicitly enabled.
- All tests pass.

## Validation Commands
- `pytest -q`
