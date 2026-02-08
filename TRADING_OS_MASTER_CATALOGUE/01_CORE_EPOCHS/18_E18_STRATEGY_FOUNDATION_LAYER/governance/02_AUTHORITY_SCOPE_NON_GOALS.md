# E18_STRATEGY_FOUNDATION_LAYER — AUTHORITY, SCOPE, NON-GOALS

AUTHORITY:
E18 has global authority over shared primitives used by strategies.

SCOPE (IN-SCOPE):
- Setup families catalogue and reference implementations (SF_*)
- Execution triggers catalogue and reference implementations (XL_*)
- Conditions catalogue and reference implementations (C_*)
- Confirmations catalogue and reference implementations (K_*)
- Candlestick foundation (named patterns + functional behaviours + contextual states)
- Levels & zones primitives (support/resistance; supply/demand; key levels)
- Market structure descriptors (trend/balance/compression/expansion states)
- Invalidation semantics vocabulary (hard/soft invalidations)
- Symbol commitment & fast context hydration (bars/indicators/news availability)
- Data lifecycle classification, reset, recovery, regeneration semantics
- Policy translation reports, coverage checklist, drift detection, compatibility verdicts

NON-GOALS (OUT-OF-SCOPE):
- Strategy alpha logic (Ross/statistical/mean reversion/value) — strategies decide
- Execution mechanics / broker routing — handled by execution layer epochs
- Capital allocation optimisation — handled by capital allocation epoch
- Auto-mutation of policies — learning is advisory only

INVARIANT:
E18 provides primitives and context; it does NOT impose strategy policy.

END
