# E18 — DATA LIFECYCLE, RESET, RECOVERY (REGENERABLE BY DESIGN)

E18 generates derived context data. This data MUST be purgeable and regenerable.

LIFECYCLE CLASSES:
A) STATIC / SLOW-CHANGING (persist across days)
- float, shares outstanding, instrument metadata

B) SESSION-SCOPED (cleared at session reset)
- intraday bars cache, VWAP state, HOD/LOD state, session zones

C) COMMITMENT-SCOPED (cleared on de-commit or end-of-day)
- symbol hydrated context, candle states, derived diagnostics

RESET MODES:
[ ] SOFT RESET: clear derived caches; keep configuration and mappings
[ ] HARD RESET: clear all foundation-generated data; revert to defaults; force rebuild
[ ] VERSION RESET: invalidate caches when foundation version changes

RECOVERY RULE:
- After reset, system may degrade to NO-TRADE until context is rebuilt.
- No silent continuation with stale caches is allowed.

INVARIANT:
Any derived artifact must declare its lifecycle class and reset behaviour.

END
