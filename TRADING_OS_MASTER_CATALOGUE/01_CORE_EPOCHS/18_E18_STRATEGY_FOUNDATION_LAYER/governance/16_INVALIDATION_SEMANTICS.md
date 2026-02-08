# E18 — INVALIDATION SEMANTICS (VOCABULARY + CONTRACT)

Strategies require explicit invalidation semantics for auditability and learning.
E18 provides a standard vocabulary and contract for invalidation events.

INVALIDATION TYPES:
- HARD_INVALIDATION (thesis broken; exit / stop required)
- SOFT_INVALIDATION (pause entries; reduce; require reconfirmation)
- TIME_INVALIDATION (setup expired)
- DATA_INVALIDATION (inputs unreliable; no-trade)

INVALIDATION CONTRACT (required fields):
- invalidation_id
- scope (setup | trigger | position | strategy)
- severity (hard | soft)
- reason_code (semantic)
- context (symbol, timeframe, level/zone involved)
- timestamp_utc

INVARIANT:
E18 defines vocabulary; strategies define which invalidations apply and when.

END
