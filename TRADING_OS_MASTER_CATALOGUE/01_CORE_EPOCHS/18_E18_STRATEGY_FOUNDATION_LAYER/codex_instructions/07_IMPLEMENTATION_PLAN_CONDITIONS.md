# E18 — IMPLEMENTATION PLAN: CONDITIONS (C_*)

Source of truth list: governance/07_CANONICAL_LIST_CONDITIONS.md

Task:
1) Implement/confirm existence of all C_* conditions as deterministic booleans.
2) Conditions must be composable and strategy-agnostic.
3) Conditions must never place trades or force policy.

Minimum deliverables per C_*:
- semantic_name: "C_<NAME>"
- component_type: condition
- evaluate(context) -> ConditionResult
- ConditionResult:
  - passed (bool)
  - measurements (optional)
  - explainability (optional)

END
