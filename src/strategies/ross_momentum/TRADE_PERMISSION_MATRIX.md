# Trade Permission Matrix — Ross Momentum (Automation)

Purpose: define when the strategy is permitted to submit new orders, when it must pause, and when it must halt.

This matrix is *mode-aware* (AM open fast vs. midday vs. late-session slower). It pairs with the policy thresholds in `strategy_policy.py`.

---

## Global hard stops (always)
- **Kill-switch** ON -> HALT
- **Daily max loss** breached -> HALT
- **3 losses rule** (max consecutive losses) -> HALT (cooling-off)
- **Data quality** insufficient for required context -> PAUSE (no new entries)

---

## A) Topping / reversal behaviour (in-trade and post-trade)
Ross frequently emphasises *being out before the topping candle fully forms*.

We implement this deterministically:
- **PAUSE new entries** when the impulse timeframe prints a topping wick ratio >= `topping_wick_ratio_pause` (default **0.50**). Manage exits only.
- **HALT / cooling-off** when the impulse timeframe prints a confirmed topping/reversal:
  - wick ratio >= `topping_wick_ratio_halt` (default **1.00**), OR
  - bearish reversal context (e.g., failure to make new highs + MACD momentum rolling over), depending on context available.

Practical interpretation:
- A *forming* long upper wick is a **warning**: stop adding, protect profits.
- A *confirmed* shooting star / heavy rejection is a **stop signal**: step aside until a reset condition occurs.

---

## B) Momentum confirmation gates (entry permission)
Before taking new entries (or re-entries):
- MACD should be **positive / trending up** (when MACD is part of the required context)
- Volume should support the move (green volume expansion vs. pullback volume contraction)
- Price should be above required structure: typically **VWAP / EMA9 / EMA20** (mode-dependent)

---

## C) Micro pullback re-entry permission
Re-entry is allowed only when pullback is **weak** and the trend is intact.

Operationally (10s execution in AM mode):
- 2–3 small red candles (weak selling)
- pullback holds above VWAP/EMA9/EMA20 per policy
- **trigger:** the next green candle breaks above the **high of the last pullback red candle**

---

## D) Volume spike safety rule (telemetry-first)
Ross often exits quickly when he sees abnormal selling pressure.

We treat this as:
- **Telemetry** captured every 10s bar: red/green volume ratios, delta volume, and failed-high attempts.
- Optional **PAUSE** condition can be enabled once validated in your own sessions (do not hard-enforce an unverified threshold).

---

## E) Level 2 / tape “iceberg” behaviour
If L2/tape context is available:
- Large hidden seller (“iceberg”) near key level -> PAUSE / exit bias
- Large buyer support -> entry bias

By default, this is advisory unless you have reliable L2 integration.
