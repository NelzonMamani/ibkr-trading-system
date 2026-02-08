# E18 — DATA LIFECYCLE, RESET, RECOVERY TASKS

Source of truth: governance/18_DATA_LIFECYCLE_RESET_RECOVERY.md

Task:
1) Classify foundation-generated data into lifecycle classes:
   - STATIC/SLOW (float, instrument metadata)
   - SESSION-SCOPED (intraday caches, VWAP/HOD/LOD state, session zones)
   - COMMITMENT-SCOPED (hydrated symbol contexts, candle states)

2) Implement reset operations:
   - Soft reset: clear derived caches; keep config + mappings
   - Hard reset: clear all foundation-generated data; revert defaults
   - Version reset: invalidate caches on foundation version bump

3) Ensure regeneration:
   - Derived context must be reconstructible from raw market data + configuration.
   - After reset, degrade to no-trade until rebuilt; no stale cache usage.

Deliverables:
- Reset command(s)/utility functions (scoped to foundation caches)
- Tests verifying reset clears correct data and preserves slow-changing data
- Documentation in SYSTEM_STATE.md referencing reset availability

END
