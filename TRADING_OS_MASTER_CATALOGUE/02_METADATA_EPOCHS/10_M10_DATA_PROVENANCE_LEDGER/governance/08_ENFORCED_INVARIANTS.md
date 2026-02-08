# ENFORCED INVARIANTS

- M10 is metadata-only (no fetching, no trading logic, no blocking).
- Any data used to generate signals or decisions MUST have a provenance record.
- Premarket prep and symbol hydration MUST be registered.
- Provenance is append-only; no silent overwrites.
- Mode relativity is mandatory: records must include mode + session_state.
- Limitations must be recorded when confidence != HIGH or freshness != REALTIME.

END
