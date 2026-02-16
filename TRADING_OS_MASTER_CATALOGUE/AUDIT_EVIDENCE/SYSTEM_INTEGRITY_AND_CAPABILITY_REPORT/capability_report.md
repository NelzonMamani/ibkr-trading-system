# Capability Reconciliation Report

- Generated: `2026-02-16T00:48:49.142555+00:00`
- Drift after reconciliation: `{'epochs_certified_in_state_but_not_in_verdicts': ['E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION', 'M10_DATA_PROVENANCE_LEDGER', 'M8_CHANGE_CONTROL'], 'epochs_certified_in_verdicts_but_not_in_state': []}`
- Recommended updates applied: `{'E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION': 'CERTIFIED'}`
- Derived crosswalk: `TRADING_OS_MASTER_CATALOGUE/CAPABILITY_CROSSWALK_DERIVED.md`
- P-layer summary: `{'inventory_path': 'AUDIT_EVIDENCE/M5/strategy_capability_inventory.json', 'matrix_path': 'AUDIT_EVIDENCE/M5/strategy_certification_matrix.json', 'strategy_count': 20, 'status_counts': {'CERTIFIED_PAPER': 19, 'PARTIAL': 1}, 'missing_capabilities': {'missing_governance': 0, 'missing_policy': 1, 'missing_tests': 0, 'not_cli_runnable': 20}}`
- E21 status: `{'present': True, 'valid': True, 'path': 'TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/E21_TRADING_READY_VERIFICATION/e21_summary.json', 'certified': True, 'status': 'CERTIFIED', 'generated_at_utc': '2026-02-15T07:33:20Z', 'checks': {'compileall_ok': True, 'live_gating_blocked': True, 'no_unhandled_exception': True, 'paper_runs_ok': True, 'pytest_ok': True, 'risk_violation_blocked': True, 'sim_runs_ok': True}}`
- Blockers: `['missing_policy:1', 'not_cli_runnable:20']`
