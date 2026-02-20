# 03 — Runtime Artefact Classification

E26 formalises a classification matrix. **Category 1** stays in git. **Category 2/3** are runtime.

## Category 1 — Canonical / Irreplaceable (MUST be in git)
- `src/` (application code)
- `tests/` (verification)
- `TRADING_OS_MASTER_CATALOGUE/` (governance + certification)
- `verification_scripts/` (operator verification tooling)
- project config (`pyproject.toml`, `requirements*.txt`, `.gitignore`, README/RUNBOOK)

## Category 2 — Regenerable runtime artefacts (MUST be gitignored)
Deletable at any time; recreated automatically.
- `data/*.db`, `data/*.sqlite`, `data/*-wal`, `data/*-shm`
- `logs/` (jsonl trace logs)
- `output/` (watchlists, trade_store.jsonl, reports)
- `data/**/runtime_cache*` (if present)

## Category 3 — Semi-persistent analytical state (MUST be gitignored; backup-able)
Important for analysis/learning but never required for boot.
- event history DB content
- regime baselines
- statistical accumulators
- backtest results
- operator exports

## Canonical locations (recommended)
These are *paths*, not code layers:

- Runtime DB root: `data/`
- Logs root: `logs/`
- Outputs root: `output/`
- Backups root: `data/backups/`

> Architecture rule: runtime state may live **outside `src/`**, while the DB *adapter and schema logic* live **inside `src/`**.

## Path override requirements
All runtime paths must be overrideable via env/config, to support:
- CI runs (tmp directories)
- multiple operators
- clean-room rebuild tests

Suggested env keys:
- `IBKR_OS_DATA_DIR` (default: `data`)
- `IBKR_OS_LOG_DIR` (default: `logs`)
- `IBKR_OS_OUTPUT_DIR` (default: `output`)

## Artefact registry (canonical contract)
The codebase must provide a single authoritative registry that lists:
- paths
- categories
- safe deletion patterns
- backup scopes

This registry is the basis for purge/reset tooling and tests.
