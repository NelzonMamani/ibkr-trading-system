# PROVENANCE EVENT MODEL

M10 uses an append-only event model. Each event describes a data element that was observed,
derived, or used, and binds it to the decision context.

## ProvenanceEvent (required fields)
- event_id: unique identifier (uuid)
- symbol: ticker or instrument identifier
- data_type: PRICE_BAR | QUOTE | ORDERBOOK | INDICATOR | ZONE | NEWS_PRESENCE | CALENDAR | REF_DATA | DERIVED_METRIC
- timeframe_scope: DAILY | HOURLY | INTRADAY | MICROSTRUCTURE | MULTI_TIMEFRAME | SESSION_LEVEL
- timeframe_resolution: 1D | 1H | 15M | 5M | 1M | 10S | TICK (as applicable)
- source_id: canonical data source identifier
- mode: SIM | PAPER | READ_ONLY | LIVE
- session_state: PRE | RTH | AH | CLOSED
- timestamp_observed: when data was observed or computed
- timestamp_used: when a decision/metric actually consumed it
- freshness_class: REALTIME | DELAYED | STALE | FROZEN | UNKNOWN
- confidence_level: HIGH | MEDIUM | LOW
- known_limitations: free-text but short; must be present if confidence != HIGH
- checksum_or_fingerprint: optional; stable hash for payload integrity if stored
- linkage:
  - signal_ids: list of M9 signal IDs generated using this data
  - decision_ids: list of decision artifact IDs (E14) that relied on this data
  - position_ids / order_ids: optional execution linkage

## Derived data rule
Derived indicators/zones MUST point back to their input provenance event_ids
(or aggregated fingerprints) so causality is traceable.

END
