# Post-merge P04 Governance Alignment Validation

## Scope
- Strategy: `P04_long_horizon_value`
- Patch intent: governance alignment only (`D10.C02` + `D3.C03`)

## Commands Run
1. `python -m compileall -q src`
2. `pytest -q`
3. `python -c "from src.metadata.strategy_policy_v2_audit import generate_audit_artifacts; generate_audit_artifacts()"`
4. Targeted certification checks via `run_audit()`.

## Verification Summary
- P04 status: `CERTIFIED`
- D10 Data Requirements: `PASS`
- No new FAIL introduced: `fail_count=0`
- 20 strategies instantiate/audited: `strategies=20`
- Baseline drift clean: `governance_lock_violations=0`

## Full Logs

### compileall (`AUDIT_EVIDENCE/post_merge_p04_compileall.log`)
```text
```

### pytest (`AUDIT_EVIDENCE/post_merge_p04_pytest_q.log`)
```text
........................................................................ [ 27%]
........................................................................ [ 55%]
............sssss....................................................... [ 83%]
............................................                             [100%]
255 passed, 7 skipped in 4.32s
```

### regenerate artifacts (`AUDIT_EVIDENCE/post_merge_p04_regenerate_artifacts.log`)
```text
[CONFIG] Loaded 152 variables
[CONFIG] HARD enforced: 30
[CONFIG] Optional: 121
[CONFIG] Scanner symbol cap: 50 (source=DEFAULT)
[CONFIG] Market data snapshot cap: 50 (source=DEFAULT)
[CONFIG] No ambiguous defaults detected
```

### targeted validation checks (`AUDIT_EVIDENCE/post_merge_p04_validation_checks.log`)
```text
[CONFIG] Loaded 152 variables
[CONFIG] HARD enforced: 30
[CONFIG] Optional: 121
[CONFIG] Scanner symbol cap: 50 (source=DEFAULT)
[CONFIG] Market data snapshot cap: 50 (source=DEFAULT)
[CONFIG] No ambiguous defaults detected
strategies=20
p04_verdict=CERTIFIED
p04_d10=PASS
fail_count=0
invalidated_count=0
governance_lock_violations=0
```
