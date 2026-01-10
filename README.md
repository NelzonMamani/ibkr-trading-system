# IBKR Modular Trading System

A phase-governed, orchestrator-centric trading platform with a safety-first focus. The system integrates
with Interactive Brokers (IBKR) for market data, prioritizes strict read-only safeguards, and uses a
Ross Cameron–style momentum scanner as the reference strategy while remaining extensible to additional
strategies.

## Authoritative Documents
The following files define system truth:
- `SYSTEM_CONSTITUTION.md` — permanent system law and safety non-negotiables.
- `SYSTEM_STATE.md` — current phase, runtime state, and acceptance criteria.
- `docs/` — phase specifications and completion records.

## What This System Is
- Multi-strategy trading platform focused on correctness, resilience, and observability.
- IBKR-integrated with strict safety controls (execution is hard-disabled by default).
- Ross Cameron momentum strategy as first-class reference for teaching-first scanner outputs.
- Designed for extension, research, and automation without requiring paid IBKR scanner features.

## Quickstart
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## How to Run
Orchestrator (system boot + loop):
```bash
python -m src.main
```

Standalone scanner (teaching + validation; import-safe):
```bash
python -m src.scanner.scanner_runner
python src/scanner/scanner_runner.py
```

## Scanner vs Orchestrator
- **Scanner** discovers/enriches symbols and produces an intelligence artifact (watchlist + 54-field rows).
- **Orchestrator** consumes scanner outputs and runs the downstream pipeline (pattern → signal → strategy → risk → execution),
  subject to the execution boundary.

Phase 27 formalises a single canonical contract between scanner and orchestrator (see `SYSTEM_STATE.md`).

## Run Modes (Safety)
- `SIM`: Offline simulation (internal-only execution simulation).
- `LIVE_READ_ONLY`: Live market data, execution hard disabled (default safe live mode).
- `LIVE_MICRO`: Limited live mode with strict safety caps (still gated).
- `LIVE`: Full live mode (explicit opt-in, guarded by configuration).

## Safety Disclaimers
- Execution is **HARD DISABLED** by default.
- LIVE_READ_ONLY must never route orders.
- Scanners are intelligence-only and never submit orders.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

## Configuration
Configuration is centralized under `src/config/` (resolver + registry). Environment variables override defaults.

Key scanner/news settings:
- `SCANNER_TOP_GAINERS_COUNT`
- `IBKR_MAX_SYMBOLS_PER_CYCLE`
- `SCANNER_TEACHING_SYMBOL_CAP` (0 disables cap; applied only in TEACHING mode)
- `SCANNER_WATCHLIST_LIMIT`
- `NEWS_ENABLED`
- `VERIFIED_RSS_PATH`

The verified RSS source list must live at the repository root: `verified_rss.txt`.

## Outputs
- Watchlists: `output/watchlists/watchlist_RossMomentum_<timestamp>.txt`
- Scanner audit artifacts: `docs/PHASE_24_SCANNER_FIELD_AUDIT.json`,
  `docs/PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md`

Refer to `SYSTEM_CONSTITUTION.md` and `SYSTEM_STATE.md` for current phase requirements and operational expectations.
