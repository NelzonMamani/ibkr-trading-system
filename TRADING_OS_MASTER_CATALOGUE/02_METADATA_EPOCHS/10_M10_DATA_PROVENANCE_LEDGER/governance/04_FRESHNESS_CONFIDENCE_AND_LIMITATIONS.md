# FRESHNESS, CONFIDENCE, AND LIMITATIONS

## Freshness classes
- REALTIME: live streaming or near-zero delay
- DELAYED: known delayed feed (e.g., 15m)
- FROZEN: broker frozen snapshot (market closed / permissions / halt scenarios)
- STALE: exceeded TTL for the declared timeframe_resolution
- UNKNOWN: cannot determine freshness reliably

## Confidence levels
- HIGH: primary expected source, within TTL, no known anomalies
- MEDIUM: derived, cached, or partial; acceptable but caution
- LOW: degraded source, partial data, missing components, or anomalies detected

## Required TTL policy (minimum)
TTL is relative to timeframe_resolution:
- 10S / 1M: seconds-to-minutes
- 5M / 15M: minutes
- 1H: hours
- 1D: day-level

Exact TTL values are configurable, but TTL MUST exist and be recorded when exceeded.

## Limitation notes (examples)
- “IBKR snapshot frozen due to market closed state”
- “RVOL baseline incomplete; RTH volume not yet available”
- “News feed unavailable; boolean defaulted to UNKNOWN”
- “Historical bars backfilled; may differ from live prints”

END
