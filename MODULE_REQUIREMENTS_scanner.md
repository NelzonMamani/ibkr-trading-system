# MODULE_REQUIREMENTS_scanner
Last updated: 2026-01-15

## 1. Purpose
The scanner is responsible for **candidate discovery** and must produce deterministic, explainable outputs.
It is not a strategy and must not trade.

## 2. Frozen Contract (Epoch 4 -> Epoch 5)
Top N gainers → Hard gates → Watchlist K → Focus M

Defaults:
- K default 15 (configurable to 30)
- M default 3–5 (configurable to 10)

Empty output is valid and must be explained.

## 3. Ross Alignment (Demand/Supply Lens)
Warrior Trading educational materials emphasize selecting stocks with:
- strong demand (gap, catalyst, attention)
- constrained supply (low float)
- high relative volume

Practical heuristics published by Ross include “20-20”: under $20 price and under 20M float as a rule-of-thumb, with exceptions under special catalysts.

## 4. Inputs
- Primary: IBKR market scanner (TOP % GAINERS etc.)
- Market snapshots: last/mark, volume, bid/ask spread
- Historical bars: previous close, average volume baseline (e.g., 20–30 day)
- Optional enrichment:
  - float (cached)
  - news/catalyst signals (tag only; avoid brittle NLP in Epoch 5)

## 5. Hard Gates (Minimum Set)
Each gate must:
- be configurable
- produce explicit drop reasons
- never crash on missing data (use flags and conservative default drops)

### 5.1 Price Gate
Config:
- min_price, max_price
Default guidance: prefer under $20; allow override.

Drop reasons:
- PRICE_TOO_LOW / PRICE_TOO_HIGH / PRICE_MISSING

### 5.2 Percent Move Gate
Config:
- min_pct_change (e.g., 10%)
Drop:
- PCT_CHANGE_TOO_LOW / PCT_CHANGE_MISSING

### 5.3 Relative Volume Gate
Config:
- min_rvol (e.g., 5.0 for Ross-style selection)
Drop:
- RVOL_TOO_LOW / RVOL_MISSING / AVG_VOL_MISSING

### 5.4 Liquidity / Spread Gate
Config:
- max_spread_abs, max_spread_pct, min_volume
Drop:
- SPREAD_TOO_WIDE / VOLUME_TOO_LOW / LIQUIDITY_LOW

### 5.5 Float Gate (Optional but supported)
Config:
- max_float (e.g., 20M preferred; allow 100M as fallback tier)
Drop:
- FLOAT_TOO_HIGH / FLOAT_MISSING (policy-configurable: missing float may be ALLOW_WITH_FLAG or drop)

## 6. Ranking and Selection
### 6.1 Survivor Score (Deterministic)
Use a weighted score based on:
- % change (normalized)
- RVOL (normalized)
- liquidity (volume)
- spread penalty
- float bonus (lower float higher score)
- catalyst flag bonus (if known)

No randomness. Tie-break by symbol to keep deterministic ordering.

### 6.2 Outputs
- WatchlistK: top K survivors by score
- FocusM: top M subset by score

## 7. State Across Cycles
Scanner must maintain:
- previous cycle survivors
- NEW/CONTINUING/DROPPED classification
- dropped reason summary per cycle
- ability to persist state in storage records

## 8. Required Outputs
### 8.1 Machine Output (ScannerArtifact)
Must contain:
- lists: topn, survivors, watchlist_k, focus_m
- per-symbol metrics and drop reasons
- reason histogram

### 8.2 Human Console Output (Operator Grade)
Every cycle prints:
- TopN count, survivors count
- DropReasons summary
- `WATCHLIST_K: [SYM,...]`
- `FOCUS_M: [SYM,...]`
- If empty: `EMPTY WATCHLIST (valid)` + reason summary

## 9. Failure and Degradation Rules
- If snapshots unavailable: treat as DEGRADED; if persistent, CRITICAL
- If IBKR scanner fails: CRITICAL for live trading
- Missing data should not crash; it should drop conservatively or flag

## References (Primary / High-signal)
The following public Warrior Trading resources informed these requirements:
- Flat Top Breakout Pattern (how Ross trades it): https://www.warriortrading.com/flat-top-breakout-pattern/
- Bull Flag pattern guide: https://www.warriortrading.com/bull-flag-trading/
- Momentum Day Trading Strategy overview: https://www.warriortrading.com/momentum-day-trading-strategy/
- Stock selection / watchlist criteria (gap/float/RVOL/catalyst concepts): https://www.warriortrading.com/day-trading-watch-list-top-stocks-to-watch/
- “20-20” heuristic (under $20, under 20M float): https://www.warriortrading.com/simplest-day-trading-strategy/
- Technical Analysis PDF (includes Micro Pullback discussion): https://media.warriortrading.com/2022/06/03110459/Technical-Analysis-v3.pdf
- Intraday Chart Patterns PDF (flat top / whole-dollar breaks etc.): https://media.warriortrading.com/2014/09/WarriorTrading-DayTradingCourse-Class5.pdf


END.
