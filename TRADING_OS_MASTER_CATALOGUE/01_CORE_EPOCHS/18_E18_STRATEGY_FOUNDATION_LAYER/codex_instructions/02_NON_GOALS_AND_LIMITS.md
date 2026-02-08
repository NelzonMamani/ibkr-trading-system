# E18 — NON-GOALS AND LIMITS (HARD)

HARD LIMITS:
- ADDITIVE FIXES ONLY (no refactors, no renames, no large rewrites)
- Do NOT alter strategy policies to “fit” the foundation
- Do NOT embed Ross-only assumptions as global gates
- Do NOT introduce new run modes (run modes remain SIM, PAPER, READ_ONLY, LIVE)

NON-GOALS:
- Implementing strategy alpha logic (Ross/statistical/mean reversion/value)
- Execution routing / broker mechanics
- Capital optimization
- Auto-mutation of strategy policies

Allowed:
- Introducing new shared foundation modules/registries/tests
- Adding adapters/shims so existing strategies can bind to semantic contracts
- Adding artifacts generation for mapping/coverage/drift reports
- Adding reset utilities for foundation-generated data (scoped to foundation caches)

END
