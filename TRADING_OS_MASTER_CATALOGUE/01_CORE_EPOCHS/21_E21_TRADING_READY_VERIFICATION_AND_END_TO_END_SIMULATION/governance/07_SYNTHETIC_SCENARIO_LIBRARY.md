# 07_SYNTHETIC_SCENARIO_LIBRARY

## Purpose
Synthetic scenarios provide deterministic test vectors for:
- setup families
- candlestick detectors
- trigger firing
- invalidation behavior
- order lifecycle

They avoid reliance on external data and allow unit-level correctness checks.

## Required scenario classes (minimum)
Each scenario is a small “market story” with bars/ticks and expected outcomes.

### Market-state scenarios
- CLOSED / holiday / weekend
- PRE session with gap semantics
- RTH open spike then consolidation
- AFTER session drift

### Data-quality scenarios
- Missing bid/ask
- Frozen quotes
- Delayed data
- OTC/untradable symbol flagged
- Subscription missing flags surfaced

### Pattern and setup scenarios (examples)
- Micro pullback (2 and 3 red candles) → trigger on reclaim
- Bull flag / tight flag compression → break & hold trigger
- Flat top breakout with repeated rejection then break
- VWAP reclaim with retest confirm
- Failed breakout → reversal gate triggers and entries blocked
- Parabolic exhaustion candle then topping sequence → entries halted

### Execution and lifecycle scenarios
- Partial fill then remainder fill
- Reject (insufficient funds / outside trading hours) and safe handling
- Cancel then replace (if supported)
- Stop/exit triggered by invalidation

## Expected output format
Each scenario must define:
- input bars/ticks (deterministic)
- expected signals (setup/trigger/candle/level flags)
- expected intents
- expected lifecycle transitions
- expected artifacts

A scenario without explicit expectations is not a test; it is a demo.
