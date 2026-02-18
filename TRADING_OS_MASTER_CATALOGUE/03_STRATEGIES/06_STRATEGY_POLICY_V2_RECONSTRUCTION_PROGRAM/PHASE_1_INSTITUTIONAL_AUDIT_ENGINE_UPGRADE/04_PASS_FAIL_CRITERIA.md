# PASS/FAIL Criteria (Deterministic)

## Rule Hierarchy
1. CRITICAL controls must PASS.
2. MAJOR controls must PASS unless explicitly NOT_APPLICABLE with rationale.
3. MINOR controls may fail without blocking certification, but are recorded.

## Domain Verdict Computation
- PASS: all CRITICAL + MAJOR controls PASS.
- FAIL: any CRITICAL fails; or any MAJOR fails without approved NOT_APPLICABLE.
- NOT_APPLICABLE: only allowed if the domain is explicitly declared N/A by the policy with rationale and the strategy class genuinely does not require it.

## Strategy Verdict Computation
- CERTIFIED:
  - all required domains PASS
  - no CRITICAL failures
  - no default-only detection
- CONDITIONALLY_CERTIFIED:
  - no CRITICAL failures
  - some MINOR failures only
- FAIL:
  - any CRITICAL failure, OR
  - any MAJOR failure without N/A approval, OR
  - default-only detected

## Approved NOT_APPLICABLE Pattern
Because StrategyPolicyV2 does not yet expose first-class N/A flags for every domain, the policy may declare N/A using one of:

1) Dedicated notes field in the policy:
- `notes="... INTRABAR: NOT_APPLICABLE — rationale ..."`

2) Domain-specific notes (preferred):
- `execution_model.notes="INTRABAR: NOT_APPLICABLE — strategy is daily/weekly only."`

This phase requires Codex to implement a deterministic parser:
- search for patterns like:
  - `NOT_APPLICABLE`
  - `N/A`
  - `APPLICABLE`
- in policy notes fields

If no explicit N/A rationale exists, the control must be treated as missing.

## Minimum Section Thresholds (Anti-Placeholder)
Policies must meet minimum thresholds unless domain is N/A.

Defaults (intraday strategies):
- setup_families: >= 1
- triggers: >= 1
- confirmations: >= 1
- exit rules: >= 1
- required_fields: >= 3

Policies that fall below thresholds fail as default-only unless N/A rationale is declared.
