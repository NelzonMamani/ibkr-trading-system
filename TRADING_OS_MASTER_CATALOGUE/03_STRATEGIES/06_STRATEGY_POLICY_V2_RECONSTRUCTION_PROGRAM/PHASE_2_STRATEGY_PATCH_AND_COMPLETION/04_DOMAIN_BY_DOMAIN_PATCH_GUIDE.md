# 04 — Domain-by-Domain Patch Guide (Matrix V2: D0–D14)

Aligned to: `src/metadata/strategy_policy_v2_audit.py`.

## D0 — Identity
PASS: identity fields non-empty; mode notes non-empty; CLOSED semantics explicit.

## D1 — Stock Selection
PASS: selection_plan + stock_selection_law + liquidity_sanity_model.halt_policy.
Ranking model must have rationale OR NOT_APPLICABLE + token RANK.

## D2 — Setup Taxonomy
PASS: setup_families >=1 and pattern_catalog >=1.
If N/A: explicit NOT_APPLICABLE + SETUP/PATTERN.

## D3 — Conditions
PASS: confirmations list >=1 and includes at least one data-quality condition and level-behaviour condition.

## D4 — Confirmations
PASS: confirmations include liquidity/spread and volume/rvol aspects.

## D5 — Trigger Model
PASS: trigger entries >=1 with non-empty trigger_id and entry_type.

## D6 — Intrabar
APPLICABLE: phase_specs>=1 + timeframe_map>=1.
Else: NOT_APPLICABLE + token INTRABAR.

## D7 — Risk
PASS: risk_model exists; safety rules>=1 (or NOT_APPLICABLE SAFETY); session_reference_law non-empty.

## D8 — Exit
PASS: exit rules>=1 (or NOT_APPLICABLE EXIT); trailing rules>=1 (or NOT_APPLICABLE TRAIL); bailout doctrine explicit.

## D9 — Position Management
PASS: notes non-empty; scaling/partials explicit.

## D10 — Data Requirements
PASS: required_fields contains symbol,last_price and pct_change|volume|rvol; notes include pause/reject.

## D11 — Safety & Failure Modes
PASS: explicit escalation doctrine; not default-only.

## D12 — Execution Constraints
PASS: preferred_order_types >=1 and notes.

## D13 — Timeframe Authority
PASS: timeframe_map present OR session semantics sufficient; cadence rules recommended.

## D14 — Scaling Doctrine
PASS: notes non-empty; max_adds_per_position >= 0.
