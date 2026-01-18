# SETUP_FAMILIES_AND_PATTERNS.md

**Purpose:** Single catalogue of what Ross trades (setup families) and the lower-level execution patterns (micro-patterns).

## Terms
- **Setup family (macro):** the thesis / market structure (e.g., Gap & Go). Found on Daily + 5m/1m.
- **Execution pattern (micro):** the trigger for entries/adds/exits (e.g., micro pullback). Found on 1m and lower.

## Setup families (macro)
1. **Gap & Go (Opening Drive)**: high RVOL + catalyst; break premarket high / opening range with continuation.
2. **Opening Range Breakout (ORB)**: break and hold above ORH after first minutes consolidation.
3. **First Pullback / First Flag**: first controlled pullback after an initial breakout/drive; continuation entry.
4. **Micro Pullback (10s/15s execution)**: 2–3 small red candles within an uptrend; continuation entry.
5. **Bull Flag / High-Tight Flag**: consolidation after impulse; break of flag high.
6. **Break of Key Level**: premarket high, whole/half dollar, prior day high, multi-day high; with volume.
7. **ABCD continuation**: measured move / stair-step continuation after pullback.
8. **Cup & Handle (intraday)**: rounded base then tight handle; break of handle high.
9. **Momentum Reclaim**: reclaim VWAP or key EMA after shakeout, then continuation.
10. **Red-to-Green / Green-to-Red (contextual)**: used as confirmation or warning, not a stand-alone edge.
4. **Micro Pullback (10s/15s execution)**: 2–3 small pullback candles in an uptrend; entry on reclaim.
5. **Bull Flag / Tight Flag (intraday)**: tight consolidation after impulse; break of flag high.
6. **Flat-Top / Ascending Breakout**: repeated tests of resistance; break with volume.
7. **Red-to-Green Move (R2G)**: reclaims prior close; continuation with volume.
8. **ABCD Extension**: measured-move continuation; uses pullbacks and breakouts.
9. **Cup & Handle (intraday)**: base + handle; break of handle high with volume.
10. **Support/Resistance Bounce + Break**: bounce off key levels or break and reclaim.
8. **ABCD Extension**: measured move continuation after initial leg.
9. **Cup & Handle (intraday)**: rounded consolidation then handle; breakout.
10. **Half-Dollar / Whole-Dollar Break**: psychological level break with momentum.
11. **Pre-market High Break**: reclaim and hold above premarket high (often overlaps Gap & Go).
12. **Halt Resume Continuation**: volatility halt then resumption; continuation if order flow supports.
12. **Halt Resume Continuation**: volatility halt then resumption; continuation if liquidity holds.
13. **Parabolic Exhaustion (avoid/exit family)**: climactic push; treat as exit/stop-trading signal, not an entry.

## Execution patterns (micro)
A. **Micro Pullback re-entry trigger** (10s/15s): after 2–3 red candles, enter on the first green candle that *reclaims* the pullback:
- Conservative trigger: `break_above(last_red_high)`
- Aggressive trigger: `break_above(pullback_trendline)`

B. **First Pullback continuation** (1m): enter on reclaim of pullback high / break of prior candle high after 1–3 candle pullback.

C. **Breakout trigger**: enter on break of defined resistance (PMH, ORH, flag high) with momentum + volume.

D. **Failure triggers**: exit on loss of VWAP / key EMA, macro rejection at major level, or topping-tail behaviour.
