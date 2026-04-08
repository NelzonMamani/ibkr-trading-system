FILE: CODEX_E27_CONTRACTS_AND_INTERFACES.md
TITLE: DEFINE E27 CONTRACTS AND INTERFACES
END MARKER: END_OF_CODEX_INSTRUCTION

Create the following shared contracts.

---

1. ExecutionPolicy
Must support:
- build_initial_stop(...)
- build_first_target(...)
- build_trailing_rule(...)
- should_scale_in(...)
- should_pause_symbol(...)
- should_rearm_symbol(...)
- derive_level_context(...)

---

2. ExecutionPlan
Fields should include:
- symbol
- strategy_name
- setup_family
- entry_style
- side
- planned_quantity
- entry_order_spec
- initial_stop_spec
- first_target_spec
- trailing_spec
- scaling_spec
- pause_spec
- level_context
- plan_id

---

3. LifecycleRecord
Fields should include:
- symbol
- strategy_name
- parent_order_id
- stop_order_id
- target_order_id
- oca_group
- current_state
- pause_state
- filled_qty
- avg_fill_price
- realized_pnl
- unrealized_pnl
- last_trail_anchor
- last_major_level
- last_red_volume_ratio
- last_green_volume_ratio
- updated_at

---

4. RecoveryVerdict
Fields should include:
- symbol
- verdict
- reason
- repair_action
- broker_truth_snapshot

---

IMPLEMENTATION NOTES

- Prefer dataclasses or strongly typed structures already used in the codebase.
- Reuse existing models where safe, but do not overload unrelated contracts.
- Keep naming explicit and auditable.

END_OF_CODEX_INSTRUCTION
