# E18 — SYMBOL COMMITMENT & FAST CONTEXT HYDRATION (EDGE REQUIREMENT)

SYMBOL COMMITMENT is a first-class concept:
When a strategy or trader commits to a symbol, the OS must proactively hydrate context ASAP.

GOALS:
- Avoid waiting “15 minutes” to see candles/volume/indicators/news.
- Provide immediate multi-timeframe context similar to broker charts.

ON SYMBOL COMMITMENT, E18 requires hydration of (minimum):
A) Timeframes:
[ ] Daily bars (reasonable lookback)
[ ] Hourly bars (reasonable lookback)
[ ] Intraday bars (1m minimum; extensible)

B) Derived series / signals as DATA (not decisions):
[ ] Volume series
[ ] RVOL / relative volume state (if available)
[ ] VWAP series (intraday)
[ ] EMA series (as configured; e.g., 9/20/50/200 if needed)
[ ] MACD series (optional; as data)

C) Candlestick foundation outputs (computed immediately):
[ ] Named patterns
[ ] Functional behaviours
[ ] Contextual candle states

D) Levels & zones (computed immediately from available bars):
[ ] Key levels (PDC/PDH/PDL/HOD/LOD/whole/half/VWAP/EMAs as applicable)
[ ] Supply/demand zones (if implemented) OR explicit “not available”

E) News availability:
[ ] HAS_NEWS: true/false for symbol (minimum requirement)
[ ] latest_news_timestamp (optional)

COMPLETENESS FLAGS:
[ ] data_complete: true/false
[ ] missing_components list

INVARIANT:
Hydration is context provisioning. Strategies decide what to use.

END
