# E18 — IMPLEMENTATION PLAN: EXECUTION TRIGGERS (XL_*)

Source of truth list: governance/06_CANONICAL_LIST_EXECUTION_TRIGGERS.md

Task:
1) Implement/confirm existence of all XL_* triggers as mechanical event detectors.
2) Triggers do NOT decide permission; they detect events (break/retest/reclaim/etc.).
3) Triggers must expose clear inputs/outputs and be testable with fixed OHLCV sequences.

Minimum deliverables per XL_*:
- semantic_name: "XL_<NAME>"
- component_type: execution_trigger
- evaluate(context, levels/zones) -> TriggerResult
- TriggerResult includes:
  - fired (bool)
  - trigger_price/level reference
  - optional explanation

END
