# 06 — Acceptance Criteria

E26 is CERTIFIED only if ALL are true:

## Determinism & regenerability
- A fresh clone with **no** `data/`, `logs/`, `output/` can run:
  - `python -m src.core_engine.orchestrator --mode READ_ONLY --cycles 1`
  - (IBKR disconnected is acceptable; must degrade safely.)
- Bootstrap is idempotent and does not require network access.

## Weight shedding
- `purge --level HARD` deletes runtime artefacts safely.
- After HARD purge, the next orchestrator run recreates required runtime state.

## Safety
- Purge tool refuses to delete outside the known runtime roots.
- Purge tool never deletes canonical sources.

## Evidence & audit
- E26 evidence report exists and includes commands/results.
- `.gitignore` prevents runtime artefacts from being committed.

## Non-regression
- `pytest -q` remains green.
- No strategy logic changes are introduced.
