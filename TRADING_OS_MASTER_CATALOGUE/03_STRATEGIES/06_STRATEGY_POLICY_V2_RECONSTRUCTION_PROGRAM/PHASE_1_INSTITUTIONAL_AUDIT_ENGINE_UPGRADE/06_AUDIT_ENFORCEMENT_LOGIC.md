# Audit Enforcement Logic (Implementation Requirements)

## Location
Audit enforcement must live in a deterministic module, suggested:
- `src/metadata/strategy_policy_v2_audit.py`
or
- `src/integrity/strategy_policy_v2_audit.py`

(Choose the location consistent with existing M5/E23 verifiers.)

## Inputs
- Iterate over `src/strategies/*/strategy_policy_v2.py`
- Import `POLICY_V2`
- Extract counts and fields:
  - selection_plan
  - stock_selection_law
  - setup_families.families
  - trigger_model.entries
  - trigger_model.confirmations
  - exit_model.rules
  - trailing_model.rules
  - safety_model.rules
  - data_requirements.required_fields
  - intrabar_execution presence + content

## Output Artifacts
Must produce:
1. `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/STRATEGY_CERTIFICATION_REPORT.md`
2. `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_AUDIT_MATRIX_V2.md`

Report must contain:
- timestamp
- per-strategy domain verdict table
- per-strategy missing controls list
- default-only detection result
- recommended spec-only additions

## Determinism Requirements
- Sort strategies by ID (P01..P20)
- Sort domains D0..D9
- Sort control IDs within domain
- No randomization
- Use stable timestamps only for header

## Enforcement Rules
- Any CRITICAL failure => FAIL verdict
- Any default-only => FAIL verdict
- N/A requires explicit rationale in policy notes; otherwise treated as missing

## Integration
Audit results must be consumable by:
- existing M5 verifiers
- E23 reconciliation report
- system_state certified files

No runtime wiring changes allowed.
