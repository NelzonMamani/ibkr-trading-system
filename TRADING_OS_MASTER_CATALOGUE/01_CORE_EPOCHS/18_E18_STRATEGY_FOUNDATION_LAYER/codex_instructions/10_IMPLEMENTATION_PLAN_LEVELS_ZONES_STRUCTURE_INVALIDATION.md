# E18 — IMPLEMENTATION PLAN: LEVELS, ZONES, STRUCTURE STATES, INVALIDATIONS

Source of truth:
- governance/14_LEVELS_AND_ZONES_FOUNDATION.md
- governance/15_MARKET_STRUCTURE_STATES.md
- governance/16_INVALIDATION_SEMANTICS.md

Task A — Levels & Zones
- Implement level and zone primitives as neutral context objects.
- Implement interaction state vocabulary (approach/break/hold/reject/reclaim/fail).
- Supply/demand zones: if full detection not available, provide:
  - zone data model
  - explicit availability flags (available/not available)
  - no silent omissions

Task B — Market structure states
- Implement the minimum structure vocabulary from governance as deterministic descriptors.
- Expose as inputs to strategies; do not enforce policy.

Task C — Invalidation semantics
- Implement invalidation contract objects (hard/soft/time/data invalidations).
- Strategies decide when invalidations trigger; foundation provides vocabulary and structured payload.

Deliverables:
- Registries and contracts for each category
- Unit tests for deterministic derivations
- Explainability hooks where feasible

END
