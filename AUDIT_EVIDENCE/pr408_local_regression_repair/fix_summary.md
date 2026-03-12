# PR408 Local Regression Repair — Fix Summary

## Invariants preserved
- Config authority remains: **override > env > registry > default**.
- Scanner architecture unchanged: provider -> candidate metrics -> strategy ranking -> watchlist -> focus.
- READ_ONLY remains non-executable.
- PAPER mode determinism preserved.
- No scanner redesign; repairs are local and additive.

## Behavioral changes (targeted)
1. **Early-RTH focus promotion is authoritative**
   - If early-RTH discovery+catalyst promotion is satisfied, focus gate now returns pass terminally and cannot be overridden by later spread checks.

2. **Provider construction failure authority restored**
   - `run_scanner_cycle` no longer silently escapes into cached provider before trying authoritative build path.
   - Config override changes now clear scanner runtime/provider globals via canonical reset helper.

3. **Watchlist print suppression determinism improved**
   - Canonical scanner state reset is available and used in fixtures, preventing stale watchlist hash/session/cycle counters from leaking across tests.

4. **Traceability degraded marker guaranteed on connectivity failure**
   - `STATE=DEGRADED` now emits for provider connection failure even when fallback is disabled.

## Why this is minimal and architecture-safe
- Only touched scanner gating/provider failure/print-state paths and config override reset integration.
- No ranking/gating policy redesign.
- No widening of fallback permissions.
- Added explicit reset helper rather than ad-hoc per-test mutation.
