# IBKR Modular Trading System

A phase-governed, orchestrator-centric trading platform with a safety-first focus. The
system integrates with Interactive Brokers (IBKR) for market data, prioritizes strict
read-only safeguards, and uses a Ross Cameron–style momentum scanner as the reference
strategy while remaining extensible to additional strategies.

## Authoritative Documents
- `SYSTEM_CONSTITUTION.md` — permanent system law and safety non-negotiables.
- `SYSTEM_STATE.md` — current phase, runtime state, and acceptance criteria.

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the orchestrator:
```bash
python -m src.main
```

Run the standalone scanner (both modes are supported):
```bash
python -m src.scanner.scanner_runner
python src/scanner/scanner_runner.py
```

## Run Modes
- `SIM`: Simulation mode for offline testing.
- `LIVE_READ_ONLY`: Live market data, execution hard disabled.
- `LIVE_MICRO`: Limited live mode with strict safety caps.
- `LIVE`: Full live mode (explicitly opt-in and guarded by configuration).

## Safety Disclaimers
- Execution is HARD DISABLED by default and in LIVE_READ_ONLY mode.
- Scanners are intelligence-only and never submit orders.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

## Configuration
All configuration is centralized in `src/config/config_resolver.py` and
`src/config/config_registry.py`. Environment variables override defaults. Key
scanner/news settings include:
- `SCANNER_TOP_GAINERS_COUNT`
- `IBKR_MAX_SYMBOLS_PER_CYCLE`
- `SCANNER_WATCHLIST_LIMIT`
- `NEWS_ENABLED`
- `VERIFIED_RSS_PATH`

The verified RSS source list must live at the repository root: `verified_rss.txt`.

## Outputs
- Watchlists: `output/watchlists/watchlist_RossMomentum_<timestamp>.txt`
- Scanner audit artifacts: `docs/PHASE_24_SCANNER_FIELD_AUDIT.json`,
  `docs/PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md`

Refer to `SYSTEM_CONSTITUTION.md` and `SYSTEM_STATE.md` for current phase
requirements and operational expectations.
