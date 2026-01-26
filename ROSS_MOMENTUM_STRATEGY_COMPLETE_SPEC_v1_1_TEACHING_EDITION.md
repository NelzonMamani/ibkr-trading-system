# Ross Momentum Strategy — Complete Spec (Teaching Edition v1.1)

## 1) Stock Selection (Single Source of Truth)
Ross stock selection is governed by the **Ross Momentum policy** and applied by
`apply_ross_stock_selection(...)` using the policy thresholds.

**Selection ranking**
1. Percent change (mode-correct baseline)
2. RVOL
3. Float (ascending)
4. Symbol (tie-break)

**Outputs**
* **Watchlist K**: capped by `watchlist_limit_k`
* **Focus M**: capped by `focus_limit_m` (always ≤ K)

## 2) Session/Mode Handling (PRE / RTH / AH / WEEKEND / HOLIDAY)
Percent-change baselines:
* **RTH**: `last_price` vs prior close
* **PRE**: `premarket_last` vs prior close
* **AH**: `after_hours_last` vs RTH close
* **Weekend/Holiday**: last trading day close vs previous trading day close

RVOL baselines:
* `RVOL_20D`: today volume vs average of prior 20 sessions
* `RVOL_1D`: today volume vs prior session volume (if available)

## 3) Float Acquisition & Caching
Float sources are attempted in order:
1. Yahoo Finance
2. Finviz
3. Nasdaq
4. IB fundamentals (fallback / local cache)

Float records include:
* raw integer float
* formatted K/M/B
* source
* fetched timestamp
* cache-hit flag

Caching is by **symbol + session date** for reuse across a session.

## 4) Pattern Catalogue (All Required Patterns)
Implemented detectors (registered and unit-tested):
1. Gap & Go (Opening Drive)
2. Opening Range Breakout (ORB)
3. First Pullback / First Flag
4. Micro Pullback (impulse-normalised)
5. Bull Flag / High-Tight Flag
6. Break of Key Level (PMH/PDH/multi-day/whole/half)
7. ABCD continuation/extension
8. Cup & Handle (intraday)
9. Momentum Reclaim (VWAP/EMA reclaim)
10. Flat-Top / Ascending Breakout
11. Red-to-Green / Green-to-Red
12. Half-Dollar / Whole-Dollar Break
13. Pre-market High Break
14. Halt Resume Continuation
15. Parabolic Exhaustion (veto)

Parabolic exhaustion sets **veto flags** to suppress new intents.

## 5) Automation Mapping (Scanner → Strategy → Risk)
* Scanner collects **measurements only** and delegates selection to policy.
* Strategy policy applies all Ross selection gates in a single function.
* Pattern suite produces summaries → trade intents (or vetoed intents).
* Ross risk overlay runs before the global risk engine.

## 6) CLI Audit Tools
* `python -m src.strategies.ross_momentum.tools.pattern_coverage_report`
* `python -m src.tools.session_audit`
* `python -m src.tools.float_audit --symbols AAPL,MSFT,NVDA,...`

Example (session audit):
```
[SESSION_AUDIT] session_state: PRE
[SESSION_AUDIT] percent_change_baseline: {'baseline_type': 'prior_close', ...}
```

Example (float audit):
```
[FLOAT_AUDIT] symbol=AAPL raw=123456789 formatted=123.46M source=YAHOO cache_hit=False
```

## 7) Troubleshooting Appendix
* **Percent change is N/A**: verify baseline data (prior close or RTH close).
* **RVOL extreme**: confirm volume inputs and baseline volume availability.
* **Float missing**: check provider sequence and cache status.
* **Pattern coverage fails**: add detector + registry + unit test for missing pattern.

---
**End of Teaching Edition Spec**
