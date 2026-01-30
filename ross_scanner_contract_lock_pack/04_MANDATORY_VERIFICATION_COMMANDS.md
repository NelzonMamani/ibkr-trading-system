# 04 — Mandatory Verification Commands (MUST RUN AND PASS)

Run these from repo root in PowerShell.

## A) Static checks
```powershell
python -m compileall -q src
pytest -q
```

## B) Scanner standalone (Ross) — IBKR connected
Ensure TWS/IBG is running and API port is correct.
```powershell
$env:IBKR_PORT="7496"
python -m src.scanner.scanner_main --strategy ross_momentum --session PRE --topn 150
```
Expected:
- Prints `[SCANNER][IBKR][SUBSCRIPTION] instrument=STK location=STK.US.MAJOR scanCode=TOP_PERC_GAIN ... abovePrice=1 belowPrice=20`
- Returns symbols consistent with IBKR.
- Watchlist is ranked DESC by pct_change (or rank_score if used) and includes small caps only (Ross universe).

## C) Scanner standalone — IBKR disconnected
Stop TWS/IBG or set wrong port.
```powershell
$env:IBKR_PORT="7497"
python -m src.scanner.scanner_main --strategy ross_momentum --session PRE --topn 150
```
Expected:
- Provider failure clearly printed
- **No MOCK symbols**
- Universe returns `[]`
- Watchlist artifact file is still written and indicates EMPTY universe.

## D) Full system run (LIVE_READ_ONLY) — one cycle
```powershell
$env:IBKR_PORT="7496"
python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum
```
Expected:
- Orchestrator prints resolved Ross subscription parameters
- Scanner prints same IBKR subscription parameters
- Watchlist printed and persisted
- No large-cap bleed (AAPL/TSLA etc.) unless IBKR itself returns them (should not given belowPrice=20)

## E) CLOSED/PREP behavior
```powershell
python -m src.main --mode SIM --cycles 1 --strategy ross_momentum --session CLOSED
```
Expected:
- Requests TopN=150
- Produces prep report + watchlist artifact even if empty.

If any step fails, fix code and rerun until all pass.
