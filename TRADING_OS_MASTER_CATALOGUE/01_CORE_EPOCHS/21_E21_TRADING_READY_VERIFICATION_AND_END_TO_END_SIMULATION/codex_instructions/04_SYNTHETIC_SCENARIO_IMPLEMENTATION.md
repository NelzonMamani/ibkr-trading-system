# 04_SYNTHETIC_SCENARIO_IMPLEMENTATION

Codex must implement a synthetic scenario library.

Each scenario must define:
- Deterministic OHLCV or tick stream
- Expected signals (setup, candle, trigger, level)
- Expected intents
- Expected lifecycle transitions

Minimum required scenarios:
- Micro pullback continuation
- Bull flag + break
- Flat top breakout
- VWAP reclaim
- Failed breakout reversal
- Parabolic exhaustion block
- No-trade scenarios (holiday, halt, SSR)

Scenarios without assertions FAIL certification.
