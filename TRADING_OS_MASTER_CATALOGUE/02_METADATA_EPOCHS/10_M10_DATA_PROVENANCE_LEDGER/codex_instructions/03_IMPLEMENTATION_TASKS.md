# IMPLEMENTATION TASKS

1. Locate existing data access points
- market data client/provider
- indicator/zone computation (foundation)
- strategy decision creation (E14 artifacts)
- execution submission/fill events

2. Define or adopt ProvenanceEvent schema
- ensure required fields from governance exist
- add a persistence mechanism (DB table or append-only file) consistent with storage epoch

3. Register data sources
- define DATA_SOURCE_REGISTRY entries for IBKR snapshot/stream, historical bars, cache, fallbacks
- define MODE_TRUTH_MATRIX for SIM/PAPER/READ_ONLY/LIVE

4. Emit provenance events
- When observing raw data (bars/quotes/ref data): emit provenance
- When deriving indicators/zones: emit provenance with parent links
- When committing symbol/hydrating: emit control-plane provenance events

5. Linkage requirements
- Each M9 signal must reference provenance event_ids (directly or via trace context)
- Each E14 decision artifact must reference the minimum provenance chain
- Execution events should reference decision_id and relevant provenance ids

6. Retention hooks (non-destructive)
- Provide a daily rollup/prune mechanism that does not erase certified history
- Ensure end-of-day “reset” expires caches/state but preserves ledger

END
