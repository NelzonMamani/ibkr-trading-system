# ISGS-V2 Control Domains & Control Definitions

## Control ID Convention
- Domains: `D0`..`D9`
- Controls: `D{n}.C{xx}`
  - Example: `D1.C02` = Stock selection law present
- Severities:
  - CRITICAL: blocks certification
  - MAJOR: blocks certification unless explicitly waived with NOT_APPLICABLE + rationale (rare)
  - MINOR: does not block certification; recorded as gap

## Domain D0 — Identity & Scope
- D0.C01 (CRITICAL): StrategyIdentityV2 present (name, strategy_id)
- D0.C02 (MAJOR): ModeSemanticsV2 present with notes for SIM/PAPER/READ_ONLY/LIVE
- D0.C03 (MAJOR): SessionSemanticsV2 present and CLOSED semantics described

## Domain D1 — Stock Selection & Universe
- D1.C01 (CRITICAL): selection_plan present (universe + scan code + caps)
- D1.C02 (CRITICAL): stock_selection_law present (explicit, even if minimal)
- D1.C03 (MAJOR): liquidity_sanity_model present (spread max, halt/SSR handling)
- D1.C04 (MAJOR): ranking_model present OR explicit NOT_APPLICABLE with rationale

## Domain D2 — Setup Taxonomy
- D2.C01 (MAJOR): setup_families present with >=1 family OR explicit NOT_APPLICABLE
- D2.C02 (MAJOR): pattern_catalog present with >=1 pattern OR explicit NOT_APPLICABLE
- D2.C03 (MINOR): structure_model present with non-empty levels list

## Domain D3 — Triggers
- D3.C01 (MAJOR): trigger_model present
- D3.C02 (MAJOR): triggers list size >=1 OR explicit NOT_APPLICABLE
- D3.C03 (MINOR): trigger IDs stable + categories non-empty

## Domain D4 — Confirmations & Conditions
- D4.C01 (MAJOR): confirmations list size >=1 OR explicit NOT_APPLICABLE
- D4.C02 (MAJOR): contains data-quality confirmation (or equivalent gate)
- D4.C03 (MAJOR): contains liquidity/spread confirmation when strategy is intraday
- D4.C04 (MINOR): contains level-behavior confirmation (break/hold/retest) where applicable

## Domain D5 — Execution & Intrabar
- D5.C01 (CRITICAL): execution_model present
- D5.C02 (MAJOR): intrabar_execution declared APPLICABLE/NOT_APPLICABLE
- D5.C03 (MAJOR): if applicable -> phase_specs and timeframe_map are non-empty
- D5.C04 (MINOR): if applicable -> cadence rules OR explicit “none” with rationale

## Domain D6 — Risk Governance
- D6.C01 (CRITICAL): risk_model present
- D6.C02 (MAJOR): safety_model present with >=1 rule OR explicit NOT_APPLICABLE
- D6.C03 (MINOR): session_reference_law present for intraday momentum strategies

## Domain D7 — Position, Trailing, Exit
- D7.C01 (MAJOR): position_management present with explicit scale/add/partial doctrine
- D7.C02 (MAJOR): exit_model has >=1 rule OR explicit NOT_APPLICABLE
- D7.C03 (MINOR): trailing_model has >=1 rule OR explicit NOT_APPLICABLE

## Domain D8 — Data Governance
- D8.C01 (CRITICAL): data_requirements present with required_fields non-empty
- D8.C02 (MAJOR): notes specify pause/reject behavior when missing required fields

## Domain D9 — Failure Modes
- D9.C01 (CRITICAL): policy contains explicit safety escalation path
- D9.C02 (MAJOR): "default-only" policy detection must fail certification

## Default-Only Detection (Global)
A StrategyPolicyV2 is considered “default-only” if:
- It exists, but:
  - has empty setup families, triggers, confirmations, exit rules, and no intrabar doctrine,
  - and lacks explicit NOT_APPLICABLE declarations with rationale.

Default-only is always FAIL.
