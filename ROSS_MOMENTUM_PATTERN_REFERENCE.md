# ROSS_MOMENTUM_PATTERN_REFERENCE
Last updated: 2026-01-15

## 1. Purpose
Concise reference of Phase-1 Ross Momentum patterns and a validation checklist for testing the automation.

## 2. Key Concepts (High Signal)
- Momentum runners are driven by catalysts + attention.
- High relative volume is a primary “in play” indicator.
- Lower float increases the probability of large % moves.
- Many high-quality opportunities cluster early (first 1–2 hours).
- Confirmation often uses VWAP and EMA9 support; breakouts should show stronger volume than pullbacks.

## 3. Pattern Quick Reference

### 3.1 Bull Flag
- Strong move up (flagpole) + consolidation near highs
- Pullback ideally on lighter volume
- Pullback not too deep (often < 50% heuristic)
- Prefer pullback holding VWAP for long bias
- Entry: first candle to make new high after pullback
- Stop: pullback low / flag low

### 3.2 Micro Pullback
- Very small pullback (1–2 candles) after strong move
- Holds EMA9/VWAP (configurable)
- Entry: break of micro pullback high / reclaim
- Stop: low of micro pullback candle

### 3.3 Flat-Top Breakout
- Repeated taps at same resistance level
- Tight consolidation beneath
- Breakout then retest hold (often described as a micro pullback entry)
- Entry: buy the retest with tight stop under the level
- Stop: just under the line / retest low

### 3.4 ORB / Premarket High Break
- Break above PM high or opening range high early
- Confirmation: volume expansion + hold above VWAP/EMA
- Stop: below OR low or pivot low

### 3.5 Failed Breakout (Warning)
- Breakout attempt fails quickly, rejects below level
- Loss of VWAP/EMA9 shortly after attempt
- Tag as AVOID_ENTRY / EXIT_WARNING

## 4. Common Risk Flags
- OVEREXTENDED (distance from VWAP)
- SPREAD_WIDE
- HALT_RISK
- LOW_LIQUIDITY
- FAILED_BREAKOUT

## 5. Manual Validation Checklist (Use When Testing)
For each detected setup:
1) Is the stock “in play” (gap/%move + RVOL + liquidity)?
2) Is there a plausible catalyst tag (if available)?
3) Is the setup level-based (not chasing)?
4) Does pullback hold VWAP/EMA9 (for long bias) as configured?
5) Is breakout volume > pullback volume?
6) Is stop structural and tight (below pullback low / level)?
7) Does implied R:R meet configured requirement?
8) Are spreads acceptable?
9) Are data quality flags clean? If not, should risk block?

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
