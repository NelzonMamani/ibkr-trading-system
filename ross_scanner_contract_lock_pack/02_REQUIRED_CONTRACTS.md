# 02 — Required Contracts (Authoritative)

## A) Strategy → Scanner Request Contract
For each strategy, the orchestrator must construct a `ScannerRequest` (or equivalent) that includes:
- `strategy_name`
- `universe_source` (e.g., IBKR_TOP_GAINERS)
- `ibkr_scan_code` (Ross: TOP_PERC_GAIN)
- `instrument` (Ross: STK)
- `locationCode` (Ross: STK.US.MAJOR)
- `numberOfRows` (Ross: top_gainers_n; prep uses 150)
- `abovePrice` / `belowPrice` (Ross: 1..20)
- `session_phase` (PRE/REG/AFTER/CLOSED)
- `policy_name` and `ranking_intent`

This request must be logged at the point of construction.

## B) Scanner Provider Contract
`IbkrScannerProvider.get_top_gainers(limit: int)` must NOT hardcode values that conflict with the request.
It must accept (directly or indirectly) the request parameters:
- scanCode
- locationCode
- instrument
- above/below price
- numberOfRows (bounded by IBKR_MAX_SYMBOLS_PER_CYCLE)

If existing provider signature is limit-only, you must add a new method or request object while maintaining compatibility.

## C) Provider Fallback Rules
- LIVE, LIVE_READ_ONLY, LIVE_MICRO: 
  - If IBKR connect fails → return `[]` and emit `STATE=DEGRADED` + explicit reason.
  - DO NOT substitute MOCK symbols.
- SIM / PAPER:
  - MOCK may be allowed, but must be explicit and labeled, never silent.
- Standalone scanner CLI may support `--provider MOCK` explicitly.

## D) Watchlist Persistence
All runs must persist:
- `output/watchlists/watchlist_RossMomentum_<timestamp>_UTC.txt`
Include:
- subscription parameters
- session
- TopN requested vs returned
- WATCHLIST_K and FOCUS_M
- drop reasons summary

## E) Percent Change Semantics
Use session-aware percent change:
- RTH baseline: previous RTH close
- PRE/AH baseline: IBKR change% is acceptable if aligned; otherwise compute `(last - ref_close_rth)/ref_close_rth`
This must be consistent between standalone and orchestrated runs.
