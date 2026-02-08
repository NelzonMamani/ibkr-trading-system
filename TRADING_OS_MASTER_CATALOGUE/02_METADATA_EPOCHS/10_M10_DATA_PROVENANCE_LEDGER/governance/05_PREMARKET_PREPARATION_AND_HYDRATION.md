# PREMARKET PREPARATION AND ON-DEMAND HYDRATION

## Mandatory rule
All preparation that influences signals, decisions, risk, or execution MUST be registered.

This includes:
- premarket gap %, premarket high/low, prior close references
- daily levels and zones (support/resistance, supply/demand, VWAP anchors)
- float, SSR, halts, symbol metadata
- derived indicators (EMA/VWAP/ATR/RVOL baselines)
- news presence (boolean is sufficient)

## Symbol commitment (rapid hydration)
When a symbol becomes “committed” (watchlist, focus, active position, or manual commit),
the system may hydrate required datasets quickly. M10 must record:
- hydration requested timestamp
- datasets requested (timeframes, indicators, zones, news boolean)
- which datasets succeeded/failed/degraded
- readiness outcome at time of first trade decision

## Recommended provenance events for hydration control-plane
- SYMBOL_COMMITTED (mode/session aware)
- DATA_HYDRATION_REQUESTED
- DATA_HYDRATION_PARTIAL
- DATA_HYDRATION_READY
- DATA_SOURCE_DEGRADED
- DATA_STALE

These are provenance events (M10) and may be mirrored as quality signals (M9),
but they must never block strategy execution directly.

END
