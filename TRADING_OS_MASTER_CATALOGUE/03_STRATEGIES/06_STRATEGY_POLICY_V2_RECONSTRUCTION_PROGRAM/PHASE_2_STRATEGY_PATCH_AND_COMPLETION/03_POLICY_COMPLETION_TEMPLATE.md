# 03 — Policy Completion Template (StrategyPolicyV2)

## Avoid “default-only”
A policy is default-only when it has 0 content in key areas:
- setup_families.families == 0
- trigger_model.entries == 0
- trigger_model.confirmations == 0
- exit_model.rules == 0
- intrabar_execution.phase_specs == 0

If a domain is truly not applicable, you must declare:
- `NOT_APPLICABLE`
- plus a domain token (e.g., INTRABAR/TRAIL/EXIT/RANK/SETUP/PATTERN/SAFETY)
- plus rationale.

## Mandatory blocks to fill (practical checklist)
- identity (non-empty)
- mode_semantics notes for SIM/PAPER/READ_ONLY/LIVE (non-empty)
- session_semantics includes CLOSED behaviour
- selection_plan + stock_selection_law
- liquidity_sanity_model.halt_policy (explicit)
- ranking_model rationale (or NOT_APPLICABLE RANK)
- setup_families >= 1 (or NOT_APPLICABLE SETUP)
- pattern_catalog >= 1 (or NOT_APPLICABLE PATTERN)
- trigger_model.entries >= 1 (or NOT_APPLICABLE TRIGGER)
- trigger_model.confirmations >= 1 (or NOT_APPLICABLE CONFIRM)
- intrabar_execution: APPLICABLE (phase_specs+timeframe_map) or NOT_APPLICABLE INTRABAR
- risk_model exists
- safety_model.rules >= 1 (or NOT_APPLICABLE SAFETY)
- session_reference_law: pct_change_reference or gap_reference non-empty
- exit_model.rules >= 1 (or NOT_APPLICABLE EXIT)
- trailing_model.rules >= 1 (or NOT_APPLICABLE TRAIL)
- position_management.notes non-empty
- data_requirements.required_fields includes symbol,last_price and pct_change|volume|rvol
- data_requirements.notes include pause/reject language
- execution_model.preferred_order_types >= 1 and notes non-empty
