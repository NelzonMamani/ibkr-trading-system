# MODULE_REQUIREMENTS_patterns
Last updated: 2026-01-15

## 1. Purpose
The Patterns module detects chart setups and outputs **PatternResults**.
Patterns never generate orders. Patterns may recommend entry/stop ideas but cannot submit them.

## 2. Inputs
Patterns consume a per-symbol **DataSnapshot** containing:
- candles (1m minimum; optional sub-1m)
- VWAP
- EMA9 (minimum), EMA20 optional
- volume (per candle) and baseline context where available
- key levels: PM high, HOD, OR high/low
- spread/liquidity
- data quality flags

## 3. Output Contract: PatternResult (Mandatory)
PatternResult fields:
- symbol
- setup_id (string)
- detected (bool)
- direction (LONG/SHORT) (Ross momentum is long-biased; still keep interface generic)
- confidence (0..1) deterministic
- rationale_text (short)
- entry_zone (optional): level/trigger definition
- stop_suggestion (optional): structure level suggestion
- target_suggestion (optional)
- tags: list[str] (VWAP_ABOVE, EMA9_SUPPORT, HIGH_RVOL, etc.)
- risk_flags: list[str] (OVEREXTENDED, SPREAD_WIDE, HALT_RISK, FAILED_BREAKOUT, etc.)
- data_quality_flags: list[str]

## 4. Required Phase-1 Pattern Set (Ross Core)
### 4.1 ORB / Premarket High Break
Detect:
- break above PM high or opening range high early session
Confirm:
- strong volume on break, not a low-volume “poke”
- prefers holding above VWAP / EMA9
Suggest:
- entry: break+hold or breakout+retest
- stop: below OR low or last pivot

### 4.2 Micro Pullback
Detect:
- strong impulse (flagpole)
- pullback of 1–2 candles (or very small consolidation) that holds support
Confirm:
- pullback volume lighter than impulse
- holds VWAP/EMA9 for long bias
Suggest:
- entry: break of pullback high / reclaim level
- stop: low of pullback candle(s)

Ross describes micro pullbacks as reliable during fast markets; the flat-top breakout “retest” is described as a micro pullback entry.

### 4.3 Bull Flag
Detect:
- impulse then consolidation near highs
- pullback should not retrace excessively (commonly < 50% heuristic is used in Warrior Trading materials)
Confirm:
- light pullback volume, holds VWAP
Suggest:
- entry: first candle to make new high after pullback
- stop: pullback low / flag low

### 4.4 Consolidation / Flat-Top Breakout
Detect:
- repeated resistance tests (“flat top”)
- tight range under level, higher lows
Confirm:
- breakout with volume, or breakout+retest
Suggest:
- entry: breakout+retest (preferred as described in Warrior Trading flat-top article)
- stop: just under retest level / base

### 4.5 Failed Breakout (Warning)
Detect:
- breakout then immediate rejection below level
- loss of VWAP/EMA9 after breakout attempt
Output:
- PatternResult detected=true with risk_flags including FAILED_BREAKOUT
- tags include AVOID_ENTRY or EXIT_WARNING

## 5. Confidence Scoring (Deterministic)
Confidence must be explainable as sum of sub-scores, e.g.:
- level quality (more taps, cleaner)
- volume quality (breakout volume vs pullback volume)
- VWAP/EMA alignment
- spread penalty
- overextension penalty
- data quality penalty

## 6. Pattern Evaluator
- Run enabled patterns
- Select “best pattern” per symbol based on confidence
- Preserve all PatternResults for storage/audit

## 7. Test Requirements
- Standalone harness for pattern evaluation on synthetic snapshots
- Contract tests ensuring PatternResult schema stable
- Edge cases: missing VWAP, missing candles, missing volume -> data_quality_flags

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
