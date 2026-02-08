# E18 — IMPLEMENTATION PLAN: SETUP FAMILIES (SF_*)

Source of truth list: governance/05_CANONICAL_LIST_SETUP_FAMILIES.md

Task:
1) Implement/confirm existence of all SF_* setup families as reusable foundation definitions.
2) Each SF_* must be policy-neutral:
   - expose signals/structure, not “trade now” decisions.
   - allow strategies to provide thresholds/permissions.
3) Each SF_* must bind to foundation primitives (conditions/confirmations/candles/levels) via semantic contracts.

Minimum deliverables per SF_*:
- semantic_name: "SF_<NAME>"
- component_type: setup_family
- evaluate(context) -> SetupResult (deterministic)
- SetupResult includes:
  - detected (bool)
  - relevant context references (levels, zones, candle states)
  - optional explanation fields

Do NOT:
- bake in strategy-specific thresholds
- enforce Ross-only gates globally

END
