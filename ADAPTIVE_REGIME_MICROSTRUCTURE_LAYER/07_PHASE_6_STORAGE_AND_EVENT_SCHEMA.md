# Phase 6 — Storage & Event Schema Integration
Last updated: 2026-01-19

## Objective
Persist regime artifacts as first-class audit data.

## Deliverables
1) Storage
Extend TradeRecord (or equivalent) to include:
- regime_snapshot (nullable)
- regime_policy_decision (nullable)

Do not break existing schema; add fields/tables using the repo’s migration approach.

2) Event schemas
Ensure REGIME_SNAPSHOT and REGIME_POLICY_DECISION have registered schemas and are persisted.

3) Optional query helper
Add a small tool to fetch last N regime snapshots from SQLite, e.g.:
- python -m src.tools.regime_dump --limit 20

4) Tests
Add tests/test_regime_storage.py:
- Store and read back regime artifacts; verify deterministic fields preserved.

## Acceptance criteria
- A single run stores regime snapshot and policy decision when enabled.
