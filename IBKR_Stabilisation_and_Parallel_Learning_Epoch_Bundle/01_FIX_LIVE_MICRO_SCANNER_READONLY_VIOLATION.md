# 01 — FIX LIVE_MICRO SCANNER “IBKR read-only disabled by config” VIOLATION

## Problem statement (observed)
When running:
- `python -m src.main --mode LIVE_MICRO --cycles 1`
with:
- `EXECUTION_ENABLED=true`
- `IBKR_READONLY_ENABLED=false`
- `SCANNER_SYMBOLS` populated

The run panics during the **SCANNER** stage with:
- `RuntimeError: IBKR read-only disabled by config`
- followed by `RUNTIME_SAFETY_VIOLATION` and deterministic safe halt.

This is incorrect: **IBKR read-only should control order routing**, not whether the scanner can obtain **market data snapshots**.

## Root cause hypothesis (what to confirm in code)
There is currently a guard in the scanner’s market-data path (or in the broker/market adapter the scanner uses) that enforces `IBKR_READONLY_ENABLED == True` for snapshot reads.

That guard is conflating:
- “Do we allow placing orders?” with
- “Do we allow requesting market data?”

## Required behaviour (authoritative)
1. In **LIVE_MICRO**:
   - Scanner **MUST** be allowed to request market data snapshots (delayed or live as configured).
   - Order routing remains controlled by:
     - `EXECUTION_ENABLED`
     - `IBKR_ORDER_TRANSLATION_ENABLED`
     - `IBKR_ORDER_SUBMISSION_ENABLED`
     - any existing execution guard / circuit breaker logic.
2. In **LIVE_READ_ONLY**:
   - Market data snapshots are allowed.
   - Order submission must remain blocked.
3. In **SIM / PAPER**:
   - Existing behaviour remains unchanged.

## Implementation requirements
### A. Decouple market data read from “read-only”
- Identify the function/class that raises `RuntimeError("IBKR read-only disabled by config")`.
- Refactor so that:
  - market data snapshot operations are permitted whenever **IBKR connectivity is configured**, regardless of `IBKR_READONLY_ENABLED`.
  - order submission operations remain blocked when `IBKR_READONLY_ENABLED=True`.

**If you need separate flags**, introduce a clear configuration split:
- `IBKR_MARKET_DATA_ENABLED` (default True)
- `IBKR_ORDER_ROUTING_ENABLED` (derived from execution flags + readonly)

However, prefer minimal change: **keep existing env surface** and fix the incorrect guard.

### B. Update scanner stage to use the correct adapter
- Ensure scanner uses a **MarketDataAdapter** interface (or equivalent) that does not enforce order routing policy.
- If scanner currently uses a broker adapter that enforces order-routing policy, split:
  - `BrokerAdapter` (orders)
  - `MarketDataAdapter` (snapshots)
and wire scanner to `MarketDataAdapter`.

### C. Safety invariants to preserve
- LIVE/LIVE_READ_ONLY/LIVE_MICRO must still:
  - disable replay (already enforced)
  - perform deterministic panic on true safety violations
  - remain 1-share limited in LIVE_MICRO

### D. Acceptance criteria
1. With:
   - `RUN_MODE=LIVE_MICRO` (via CLI `--mode LIVE_MICRO`)
   - `EXECUTION_ENABLED=true`
   - `IBKR_READONLY_ENABLED=false`
   - `SCANNER_SYMBOLS=AAPL,TSLA,NVDA,AMD,SPY`
   - `--cycles 1`
   The system must complete the scanner stage without raising “read-only disabled”.

2. The system must still block orders when:
   - `IBKR_READONLY_ENABLED=true` OR `EXECUTION_ENABLED=false` OR submission flags are false.

3. A unit test must assert the regression:
   - scanner market-data request path does **not** depend on `IBKR_READONLY_ENABLED`.

## Code touchpoints (expected, adjust to repo reality)
- `src/scanner/*` integrated scanner stage
- `src/ibkr/*` adapters / readonly / live broker integration
- `src/config/*` resolver/guards
- `src/core/orchestrator.py` stage wiring and safety violation handling

## Mandatory Verification Commands (must run and report)
After implementing the fix, run and paste a short report:
1. `python -m compileall -q src`
2. `pytest -q`
3. PowerShell env setup (example):
   - `$env:LIVE_MICRO_ACK="true"`
   - `$env:LIVE_MICRO_1_SHARE_ONLY="true"`
   - `$env:LIVE_MICRO_MAX_POSITIONS="5"`
   - `$env:LIVE_MICRO_MAX_DAILY_LOSS="10"`
   - `$env:EXECUTION_ENABLED="true"`
   - `$env:IBKR_READONLY_ENABLED="false"`
   - `$env:IBKR_ORDER_TRANSLATION_ENABLED="true"`
   - `$env:IBKR_ORDER_SUBMISSION_ENABLED="true"`
   - `$env:SCANNER_SYMBOLS="AAPL,TSLA,NVDA,AMD,SPY"`
4. `python -m src.main --mode LIVE_MICRO --cycles 1`

### Verification report format (required)
- Summary: PASS/FAIL
- If FAIL: list the first failing command and the stack trace excerpt; fix and rerun until PASS.
- Include the scanner-stage log line confirming it used market snapshots without triggering read-only error.

END
