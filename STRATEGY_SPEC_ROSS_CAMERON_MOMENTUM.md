# STRATEGY_SPEC_ROSS_CAMERON_MOMENTUM
Last updated: 2026-01-15

## 1. Scope
Engineering specification for an intraday momentum strategy class aligned to Ross Cameron / Warrior Trading educational methodology.
This is not financial advice. The objective is to build a deterministic automation implementation.

## 2. Market Thesis (Demand vs Supply)
Ross momentum education consistently frames momentum runners as:
- **High demand**: catalysts + attention + strong % move
- **Low supply**: low float amplifies moves
- **High urgency**: early session activity concentrates opportunity

## 3. Stock Selection (Scanner Alignment)
Common published criteria across Warrior Trading materials include:
- **Gap / % move**: meaningful % change (often +10% as a typical floor; configurable)
- **High relative volume**: often very high; published selection guidance uses ~5x RVOL as a minimum for “in play” candidates (configurable)
- **Price preference**: “20-20” heuristic suggests under $20 price (exceptions exist)
- **Float preference**: “20-20” heuristic suggests under 20M float; watchlist materials emphasize under ~20M as a higher-move likelihood
- **Catalyst**: news/earnings/FDA/other reason for movement

The Trading OS scanner must operationalize these as gates + rank factors, not as fixed constants.

## 4. Core Setups (Phase-1)
### 4.1 Bull Flag
A strong initial move (“flagpole”) followed by a pullback or consolidation near highs; continuation on breakout.
Warrior Trading guidance includes:
- pullback ideally lighter volume
- pullback not too deep (often < 50% heuristic)
- should not break below VWAP for long bias
- entry on new high after pullback

### 4.2 Micro Pullback
A very small pullback (often 1–2 candles) after a strong move, followed by continuation.
Often used during fast-moving markets.
Stops commonly relate to the pullback candle low.
Warrior Trading flat-top breakout article explicitly describes the breakout retest as a micro pullback entry type.

### 4.3 Flat-Top Breakout (Consolidation Breakout)
Repeated resistance tests at the same level, tight range, then breakout.
Warrior Trading flat-top guidance emphasizes waiting for breakout, then a retest, then buying the retest with a tight stop under the level.

### 4.4 ORB / Premarket High Break
Break above premarket high or opening range high early, often with volume confirmation.

### 4.5 Failed Breakout (Avoid/Exit)
Breakout attempt fails quickly and price rejects below level; used as warning to avoid entry or tighten/exit.

## 5. Confirmation and Filters (Gold Standard Behaviour)
Strategy should prefer entries where:
- price holds above VWAP and/or EMA9 on pullbacks
- breakout volume exceeds pullback volume
- spread and liquidity are acceptable
- entry is level-based (not chasing extension)

## 6. TradeIntent Contract
Strategy outputs TradeIntent (no broker orders):
- symbol, side, setup_id
- entry trigger definition (level + condition)
- stop plan (structure-based)
- optional targets / scaling notes (if used)
- validity window (time-of-day aware)
- rationale_text and tags

## 7. Risk Management Philosophy (Implementation Guidance)
Warrior Trading educational framing emphasizes:
- tight, structural stops
- quick recognition when a trade is not working
- avoid chasing when market is not in “feeding frenzy” conditions

Automation should implement:
- mandatory stop plan per intent
- compute implied risk per share and implied R multiple
- allow risk engine to block intents that do not meet configured constraints

## 8. Time-of-Day Bias (Configurable)
- early session: higher priority for entries
- later session: reduced aggressiveness or stricter filters

## 9. Non-Goals (Epoch 5)
- No silent adaptive mutation of rules
- No fundamental/long-horizon Buffett logic (Epoch 6 only)

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
