# IBKR Modular Trading System

A phase-governed, orchestrator-centric trading platform with a safety-first focus.

- Multi-strategy trading platform focused on correctness, resilience, and observability.
- IBKR-integrated with strict safety controls (execution is hard-disabled by default).
- Ross Cameron momentum strategy is the first-class reference scanner (teaching-first).
- Designed for extension and research without requiring paid IBKR scanner subscriptions.

## Authoritative Documents (Source of Truth)
The following files define system truth and must be kept in sync:
- `SYSTEM_CONSTITUTION.md` — permanent system law and safety non-negotiables.
- `SYSTEM_STATE.md` — current phase, known issues, acceptance criteria, and operational expectations.

## Quickstart
```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## How to Run

Run the standalone scanner (teaching + resilience baseline):
```bash
python -m src.scanner.scanner_runner
# also supported (script mode)
python src/scanner/scanner_runner.py
```

Run the orchestrated system:
```bash
python -m src.main
```

## Current Status
- Scanner runner: operational and resilient (Phase 24 complete).
- Orchestrator boot: currently blocked by execution-layer import hygiene (Phase 25 active).
  - Example symptom: `ModuleNotFoundError: No module named 'utils'` originating from execution modules.
  - Fix scope: refactor invalid imports, and ensure execution layer cannot prevent startup when execution is disabled.

Refer to `SYSTEM_STATE.md` for current phase authority and acceptance criteria.

## Configuration
Configuration is centralized under `src/config/` (resolver + registry). Environment variables override defaults.

Key scanner/news settings:
- `SCANNER_TOP_GAINERS_COUNT`
- `IBKR_MAX_SYMBOLS_PER_CYCLE`
- `SCANNER_TEACHING_SYMBOL_CAP`
- `SCANNER_WATCHLIST_LIMIT`
- `NEWS_ENABLED`
- `VERIFIED_RSS_PATH`

## Verified RSS Sources
`verified_rss.txt` must live at the repository root and is the only authoritative allowlist for RSS sources.
