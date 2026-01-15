# ROSS_MOMENTUM_PATTERN_DETECTION_BLUEPRINT
Last updated: 2026-01-15

## 1. Purpose
Defines deterministic detection blueprints for Ross Momentum Phase-1 patterns.
Each detector must be explainable and output PatternResult.

## 2. Shared Inputs and Pre-computed Levels
Inputs per symbol:
- 1m candles (required), optional sub-1m candles
- VWAP
- EMA9 (required), EMA20 optional
- volume per candle
- key levels:
  - PM_HIGH (premarket high)
  - OR_HIGH / OR_LOW (opening range for first N minutes)
  - HOD (high of day)
  - WHOLE_DOLLAR levels (optional)
- spread and liquidity
- data quality flags

## 3. Output: PatternResult Schema (Required)
- setup_id
- detected
- direction (LONG/SHORT)
- confidence (0..1)
- rationale_text
- entry_zone (optional)
- stop_suggestion (optional)
- target_suggestion (optional)
- tags
- risk_flags
- data_quality_flags

## 4. Detector Blueprints

### 4.1 Bull Flag Detector
**Context:** strong impulse leg up, then consolidation/pullback near highs.

**Detection heuristics (deterministic):**
- identify impulse: consecutive green candles with increasing range and volume above baseline
- pullback phase: 1–5 candles down/sideways
- retracement depth: pullback retrace <= configured percent (default 50% heuristic)
- VWAP rule: pullback does not break below VWAP (configurable strictness)
- volume rule: pullback volume average < impulse volume average

**Entry suggestion:**
- “first candle to make a new high after pullback” (break of pullback high)

**Stop suggestion:**
- pullback low / flag low

**Risk flags:**
- OVEREXTENDED if distance from VWAP > configured threshold
- SPREAD_WIDE if spread too large

### 4.2 Micro Pullback Detector
**Context:** fast markets; tiny pullback after impulse.

**Detection:**
- impulse leg up (as above)
- micro pullback: 1–2 small red candles OR tight 2–3 candle pause
- support: holds above EMA9 and/or VWAP (configurable)
- pullback volume lighter than impulse

**Entry:**
- break of micro pullback high / reclaim of level

**Stop:**
- micro pullback candle low

### 4.3 Flat-Top Breakout Detector
**Context:** repeated resistance tests at same level (“flat top”), then breakout and retest.

**Detection:**
- resistance level touched ≥ 2 times with small tolerance
- higher lows or tightening range below resistance
- breakout candle closes above resistance with volume expansion
- optional retest: price returns to the level, holds (micro pullback)

**Preferred entry:**
- breakout THEN retest hold (as described by Warrior Trading)

**Stop:**
- just under the level / retest low

### 4.4 ORB / Premarket High Break Detector
**Detection:**
- define OR as first N minutes; compute OR_HIGH/OR_LOW
- detect break above OR_HIGH or PM_HIGH
- confirm with volume expansion and hold above VWAP/EMA

**Entry:**
- breakout+hold, or breakout+retest

**Stop:**
- below OR_LOW or pivot low

### 4.5 Failed Breakout Detector (Warning)
**Detection:**
- breakout above level then rapid rejection below the same level
- large upper wick / rejection candle
- loss of VWAP/EMA9 shortly after attempt

**Output:**
- PatternResult detected=true, tags include AVOID_ENTRY, risk_flags include FAILED_BREAKOUT

## 5. Confidence Scoring (Explainable)
Confidence must be computed as sum of fixed sub-scores:
- Level quality (touch count, tightness)
- Volume quality (breakout vs pullback)
- VWAP/EMA alignment
- Spread penalty
- Overextension penalty
- Data quality penalty

## 6. Validation/Tests
- synthetic candle fixtures for each pattern
- contract tests for PatternResult schema
- missing data tests produce data_quality_flags

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
