# RUNBOOK — IBKR Trading System (Epoch 5)

Last updated: 2026-01-15

## Purpose
This runbook provides **copy/paste commands** to run the scanner, doctor bootstrap, and the full orchestrator from the repository root. The system must be started from the repo root using `python -m ...` to avoid import instability.

## Quickstart (Repo Root)

### 1) Doctor (imports + config + 1 scanner cycle)
Runs a single safe scanner cycle in READONLY mode and exits.

```bash
python -m src.core_engine.doctor
```

### 2) Scanner Standalone (1 cycle, READONLY)
Runs the scanner once and prints TopN, survivors, WatchlistK, and FocusM.

```bash
python -m src.scanner.scanner_runner --mode READONLY --cycles 1
```

### 3) Orchestrator (deterministic cycles)
Runs the full system under the deterministic orchestrator. Use the `--mode` flag for SIM/READONLY/LIVE_1SHARE.

```bash
# SIM (safe, no broker orders)
python -m src.core_engine.orchestrator --mode SIM --cycles 1

# READONLY (live data, no broker orders)
python -m src.core_engine.orchestrator --mode READONLY --cycles 1

# LIVE_1SHARE (1-share live testing, broker orders allowed only if risk-approved)
# WARNING: requires explicit operator approval + IBKR connectivity. Never use in SIM/READONLY.
python -m src.core_engine.orchestrator --mode LIVE_1SHARE --cycles 1
```

## Troubleshooting

### Module import errors
- Ensure you are running **from repo root**.
- Use `python -m ...` (not `python src/...`).

### IBKR connectivity
- Verify TWS/Gateway is running and reachable on the configured host/port.
- For READONLY mode, ensure `IBKR_READONLY_ENABLED=true` if required by your environment.

### Missing data / empty watchlist
- Empty watchlists are valid. The scanner will print `EMPTY WATCHLIST (valid)` and drop reasons.
- Check scanner gate thresholds if you consistently see empty output.

END.
