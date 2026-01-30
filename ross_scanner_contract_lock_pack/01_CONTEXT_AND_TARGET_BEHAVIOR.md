# 01 — Context and Target Behavior (Authoritative)

## What is broken
- Ross Momentum watchlist symbols in the main system drift away from IBKR scanner symbols.
- Large-cap symbols (AAPL/TSLA/PLTR/etc.) appear in Ross watchlist, which is unacceptable.
- The scanner can run in standalone but when IBKR connection fails it silently falls back to MOCK symbols, masking the issue.
- Ranking/sorting is performed in multiple layers (scanner_runner, orchestrator, strategy_policy), creating inconsistent ordering.

## Non-negotiable target behavior
1. **Ross Momentum MUST be strategy-bound at the scanner contract level.**
   - For Ross: `ScannerSubscription(instrument="STK", locationCode="STK.US.MAJOR", scanCode="TOP_PERC_GAIN", abovePrice=1, belowPrice=20, numberOfRows=top_gainers_n)`
   - `top_gainers_n` defaults to **150** for prep mode and **50** for live trading modes unless configured otherwise.

2. **If IBKR is unavailable, Ross scanner returns an explicit EMPTY universe** (not MOCK) in live modes.
   - Empty watchlist is correct behavior; system must not look "dead" but must produce a preparation report and clear diagnostics.

3. **Preparation when market is closed (or outside RTH)**
   - System must still produce a deterministic "prep report" and a persisted watchlist output file (even if empty).
   - Prep should request **Top N=150** from IBKR (when available) and run cheap filters (price/gap/rvol/float/liquidity/spread/data quality).
   - Output: watchlist K=15, focus M=5 + drop reasons summary.

4. **Single ranking authority**
   - Final ranking for Ross watchlist selection must be owned by ONE layer only (choose and enforce).
   - Recommended: strategy policy does final ranking; scanner provides facts + gate checks only.

5. **Prints must prove correctness**
   - Every run prints the exact IBKR subscription parameters used for Ross.
   - Every run prints provider used (IBKR vs MOCK) and reason.
   - Every run prints universe count, gated survivors, watchlist K, focus M, NEW/CONTINUING/DROPPED.

## Safety
- Never introduce trading in a mode that is read-only.
- No replay in LIVE/LIVE_READ_ONLY/LIVE_MICRO.
