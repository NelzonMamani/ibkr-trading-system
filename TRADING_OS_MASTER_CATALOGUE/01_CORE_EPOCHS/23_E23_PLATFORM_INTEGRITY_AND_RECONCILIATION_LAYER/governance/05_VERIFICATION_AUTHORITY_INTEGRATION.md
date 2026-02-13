# 05_VERIFICATION_AUTHORITY_INTEGRATION.md
# E23 — Integration with M5_VERIFICATION_AUTHORITY
Last updated: 2026-02-13

## Requirement
E23 must treat the existing verification system as the source of evidence truth.

E23 must:
1) Discover available verification scripts/tests and map them to epochs.
2) Use a registry to define per-epoch "how to prove this is working".
3) Execute verifications when evidence is missing/stale.
4) Produce evidence pointers and reproducible commands.

## Epoch Verification Registry
A registry file must exist (YAML or JSON), for example:
- src/integrity/epoch_verification_registry.yaml

Registry entries contain:
- id: "E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER"
- verify:
  - type: "pytest"
    cmd: "pytest -q path/to/tests"
  - type: "command"
    cmd: "python -m src.main --mode SIM --cycles 1"
- required_artifacts:
  - "AUDIT_EVIDENCE/*.json"
- acceptance:
  - "exit_code == 0"
  - "no invariant violations in report"

## Evidence Freshness
E23 may accept existing evidence if:
- evidence exists AND
- evidence refers to current code base (commit hash or timestamp after last merge baseline)
OR operator explicitly allows reuse via config flag.

Default behavior:
- rerun "fast" verification (compileall + pytest -q) and regenerate docs.

END
