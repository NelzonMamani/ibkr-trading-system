# PHASE_26C_CANDLESTICK_LIBRARY_IMPLEMENTATION

## Objective
Implement a **broad candlestick recognition library** (single-candle and multi-candle) that can be used across strategies as **supporting evidence**, never as a standalone trigger.

This library must integrate by producing evidence tags and optional micro-rationale that attach to `PatternResult.setup_quality_tags` or a dedicated `candle_evidence` field (if added with versioning).

## Scope
### In-Scope
Single-candle recognisers (minimum set):
- Doji (context)
- Hammer / Hanging Man
- Shooting Star / Inverted Hammer
- Marubozu
- Long upper wick / long lower wick classification

Multi-candle recognisers (minimum set):
- Bullish Engulfing / Bearish Engulfing
- Morning Star / Evening Star
- Three White Soldiers / Three Black Crows
- Tweezer Top/Bottom

### Out-of-Scope
- Using candle recognisers as entry triggers in Ross mode
- Exotic low-frequency candle patterns (can be added later)

## Engineering Rules
- Deterministic: identical candles → identical classification
- Stateless: no hidden globals
- Fast: O(n) per candle window, safe for intraday loops

## Files to Create/Modify (Repo)
- Create: `src/strategies/common/candles/candle_types.py`
- Create: `src/strategies/common/candles/single_candle.py`
- Create: `src/strategies/common/candles/multi_candle.py`
- Create: `src/strategies/common/candles/candle_evidence.py` (helpers to attach evidence)

## Definition of Done
- Library can be imported and run standalone on a list of OHLC candles.
- Returns structured evidence objects/tags with rationale.
- Ross core patterns can optionally attach candle evidence without changing trigger logic.
