# Diagnostics Inventory (Ross + runtime readiness)

| Script | Layer | Purpose | Key Inputs | Example Usage | Output/Artifact |
|---|---|---|---|---|---|
| `verification_scripts/verify_float_wiring.py` | Float | Verify canonical float cache wiring and source selection | runtime env/config | `python verification_scripts/verify_float_wiring.py` | stdout + audit evidence |
| `verification_scripts/verify_session_detection.py` | Session | Validate session detection and labels | optional env overrides | `python verification_scripts/verify_session_detection.py` | stdout |
| `verification_scripts/verify_ross_closed_prep_mode.py` | Prep/session | Prove CLOSED/weekend reference behavior | none | `python verification_scripts/verify_ross_closed_prep_mode.py` | `AUDIT_EVIDENCE/ross_session_hardening/closed_prep_verification_report.json` |
| `verification_scripts/run_scanner_simulation.py` | Scanner | Verify scanner/watchlist/focus path | scanner config | `python verification_scripts/run_scanner_simulation.py` | stdout + scanner payload |
| `verification_scripts/verify_policy_v2_resolver_runtime.py` | Policy | Reconcile policy resolver with runtime | none | `python verification_scripts/verify_policy_v2_resolver_runtime.py` | stdout/json |
| `verification_scripts/ross_live_execution_proof_pipeline.py` | Execution/risk/storage | Explicit execution lifecycle proof tool | `ENABLE_TEST_PIPELINE`, `TEST_PIPELINE_MODE`, symbol | `ENABLE_TEST_PIPELINE=true TEST_PIPELINE_MODE=DRY_RUN python verification_scripts/ross_live_execution_proof_pipeline.py --from-watchlist` | `AUDIT_EVIDENCE/ross_execution_proof/test_pipeline_*.json` |
| `verification_scripts/verify_ibkr_spot_check.py` | Broker | Broker connectivity spot check | IBKR envs | `python verification_scripts/verify_ibkr_spot_check.py` | stdout |
| `verification_scripts/list_diagnostics_inventory.py` | Discovery | Enumerate available high-value diagnostics | none | `python verification_scripts/list_diagnostics_inventory.py` | stdout inventory listing |

