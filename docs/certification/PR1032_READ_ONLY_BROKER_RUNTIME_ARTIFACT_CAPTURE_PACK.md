# PR1032 READ_ONLY Broker-Connected Runtime Artifact Capture Pack

## Scope

PR1032 provides the artifact capture pack required after PR1031. It defines the evidence bundle and operator runbook that must be used during a future broker-connected READ_ONLY runtime session before any PAPER enablement decision can be considered.

This PR does not certify that a broker-connected session has already completed. It creates a strict capture contract, manifest template, operator runbook, acceptance gates, rejection conditions, and review checklist for the future run.

No PAPER/LIVE enablement was added. No production trading behavior was changed. No trading thresholds were changed. No Ross scanner, float, RVOL, gap, catalyst, setup, decision, risk, mapping, or execution rule was weakened. No fake numeric targets, fake R:R, fake partials, fake trailing, fake lifecycle evidence, or fake broker orders were added.

## Executive Verdict

```text
PAPER_READY: NO
BROKER_CONNECTED_READ_ONLY_ARTIFACT_CAPTURE_PACK: READY_TO_RUN
OPERATOR_RUNBOOK_ADDED: YES
OPERATOR_RUNBOOK_ACKNOWLEDGEMENT_CAPTURED: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED: NO
BROKER_ORDER_AUDIT_CAPTURED: NO
DURABLE_STORAGE_READBACK_CAPTURED: NO
PAPER_READINESS_GATE: FAIL
PRODUCTION_CODE_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
PAPER_LIVE_ENABLED: NO
NEXT_REQUIRED_ACTION: Run a real broker-connected READ_ONLY session using the PR1032 operator runbook and capture pack, redact/hash the artifact bundle, and review every acceptance gate before any PAPER decision.
DO_NOT_GO_PAPER_REASON: PR1032 only prepares the broker-connected READ_ONLY operator runbook and artifact capture pack; it does not contain captured broker runtime evidence, operator acknowledgement, zero-order broker audit proof, durable storage readback proof, numeric R:R certification, or partial/trailing/breakeven lifecycle certification.
```

PAPER readiness remains blocked. The capture pack and operator runbook are ready to use, but a real broker-connected READ_ONLY session artifact has not been captured by this PR.

## Capture Pack Contents

| File | Purpose | Status |
| --- | --- | --- |
| `docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md` | Operator-facing pre-run, run, abort, redaction, hashing, and post-run validation instructions. | Added |
| `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json` | Machine-readable manifest template for the future broker-connected READ_ONLY artifact bundle. | Updated to require runbook acknowledgement |
| `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_CAPTURE_PACK.md` | Human-readable capture protocol, evidence matrix, rejection rules, and readiness verdict. | Updated |
| `tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py` | Regression tests that pin the capture-pack/runbook contract and prevent PAPER-readiness overclaiming. | Updated |

## Required Operator Run Constraints

The future artifact capture run must satisfy all of these constraints before it can be reviewed:

| Constraint | Required value | Failure condition |
| --- | --- | --- |
| Operator runbook | `PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md` acknowledged before broker connection | Missing acknowledgement artifact |
| `RUN_MODE_EFFECTIVE` | `READ_ONLY` | Any `PAPER` or `LIVE` effective mode |
| `EXECUTION_ENABLED_EFFECTIVE` | `false` | `true` or missing value |
| `EVENT_REPLAY_MODE_EFFECTIVE` | `OFF` | Any replay mode active in the broker-connected run |
| IBKR API write access | `false` | API write access enabled |
| IBKR order submission | `false` | Order submission enabled |
| `FORCE_CLEAN_START` | `false` | Clean-start, flatten, or cancel-all path enabled |
| Broker order mutations | `0 submitted`, `0 cancelled`, `0 modified` | Any broker order mutation |
| Artifact redaction | Account/secrets redacted or absent | Unredacted account id, token, credential, host secret, or session secret |
| Artifact hashing | SHA-256 for every file | Missing hash or changed file after review |

## Required Artifact Bundle

| Artifact id | Required evidence | Must prove | Status in this PR |
| --- | --- | --- | --- |
| `operator_runbook_acknowledgement` | Runbook path, operator, acknowledgement time, pre-run checklist result, abort-condition review, `PAPER_READY=NO`. | Operator used PR1032 runbook before broker connection. | Template only |
| `runtime_config_snapshot` | Runtime mode/effective mode, execution flags, event replay mode, IBKR write/order flags, clean-start flag. | READ_ONLY, execution disabled, replay OFF, clean-start disabled. | Template only |
| `broker_connection_snapshot` | Connected status, host/port/client id, market data type, redacted account id. | Broker connection was market-data/read-only shaped. | Template only |
| `scanner_cycle_artifact` | Provider source, scanner contract, top-N, drop ledger, selection spec. | Scanner contract valid with no manual/prep survivor. | Template only |
| `catalyst_news_artifact` | News source mode, as-of time, catalyst status by symbol, fresh/stale counts. | Catalyst is explicit for every focused symbol. | Template only |
| `watchlist_focus_artifact` | Watchlist K, focus M, row-level source/provenance. | Focus is subset of watchlist; no manual focus or prep seed. | Template only |
| `pattern_input_artifact` | Timeframe provenance, data quality flags, liquidity, levels, indicators, news context. | Inputs are fresh/provenanced or blocked with persisted reason. | Template only |
| `setup_decision_artifact` | Detected setups, selected setup, entry/stop/target model, rationale, decision reason. | READ_ONLY decision path persists trade-plan evidence without PAPER override. | Template only |
| `risk_gate_artifact` | Risk called/approved flags, reason, profile, vetoes. | Risk decision is persisted for intents and not fabricated for no-trade paths. | Template only |
| `execution_gate_artifact` | Execution enabled, order submission enabled, API write allowed, execution path, order attempt count. | Order submission disabled and order attempts zero. | Template only |
| `broker_order_audit` | Submitted/cancelled/modified counts plus open orders before/after. | Zero broker order mutations. | Template only |
| `analytics_storage_artifact` | Write/readback counts, trade-plan records, no-trade records, artifact paths. | Durable storage artifacts are written and read back. | Template only |
| `final_verdict` | PAPER verdict, blockers, operator review signature. | `PAPER_READY=NO` unless every objective gate passes. | Template only |

## Operator Runbook Summary

The operator runbook requires the future operator to:

1. Confirm READ_ONLY-only intent before connecting to the broker.
2. Create a fresh artifact directory.
3. Capture and review the runtime config snapshot before broker connection.
4. Abort if PAPER/LIVE, executable order authority, clean-start, flatten, cancel-all, or order mutation paths are enabled.
5. Connect only for broker market data/read-only observation.
6. Capture scanner, catalyst/news, watchlist/focus, pattern input, setup/decision, risk, execution gate, broker order audit, analytics/storage, and final verdict artifacts.
7. Redact account ids, tokens, credentials, host secrets, and session secrets.
8. Compute SHA-256 for every artifact file after redaction.
9. Keep `PAPER_READY=NO` unless every objective gate passes and unresolved numeric R:R/lifecycle blockers are separately resolved.

## Acceptance Gates

| Gate | Required pass condition | Current PR1032 result |
| --- | --- | --- |
| Operator runbook acknowledged | Operator acknowledgement artifact exists and pre-run checklist completed before broker connection. | Not captured |
| READ_ONLY mode only | Runtime artifact proves effective mode is READ_ONLY. | Not captured |
| Clean-start disabled | Runtime artifact proves `FORCE_CLEAN_START=false` and no flatten/cancel-all workflow ran. | Not captured |
| Zero broker order mutations | Broker audit proves submitted/cancelled/modified counts are all zero. | Not captured |
| Scanner/focus artifact present | Scanner, watchlist, focus, and drop ledger artifacts are present and hashed. | Not captured |
| Catalyst/news artifact present | Catalyst/news source and status evidence are present and hashed. | Not captured |
| Setup/decision/risk artifact present | Setup, decision, target-model, rationale, and risk records are present and hashed. | Not captured |
| Execution gate artifact present | Execution/order authority is disabled and order attempts are zero. | Not captured |
| Durable storage readback | Trade/no-trade records are written and read back from storage. | Not captured |
| Redaction and hashing | Every artifact is redacted or verified secret-free, and every file has SHA-256. | Template only |

Final gate result: `PAPER_READINESS_GATE: FAIL`.

## Hard Rejection Rules

A future artifact bundle must be rejected immediately if any of these are observed:

1. Missing `operator_runbook_acknowledgement` artifact.
2. `RUN_MODE_EFFECTIVE=PAPER` or `RUN_MODE_EFFECTIVE=LIVE`.
3. `EXECUTION_ENABLED_EFFECTIVE=true`.
4. `IBKR_ORDER_SUBMISSION_ENABLED=true` or equivalent order submission authority.
5. `FORCE_CLEAN_START=true`.
6. Any clean-start, flatten, cancel-all, or broker order reconciliation mutation workflow starts.
7. Any submitted, cancelled, modified, preview-submitted, or staged broker order.
8. Any synthetic broker order, fake trade, fake lifecycle event, or fabricated storage record.
9. Missing runtime config snapshot.
10. Missing broker order audit.
11. Missing durable storage readback evidence.
12. Missing scanner/watchlist/focus artifact.
13. Missing setup/decision/risk artifact for an intent path.
14. Unredacted account id, token, credential, host secret, or session secret.
15. Missing SHA-256 hash for any artifact file.

## Review Checklist For The Future Broker-Connected Run

1. Confirm artifact bundle uses the PR1032 manifest schema.
2. Confirm the operator runbook acknowledgement exists and precedes broker connection.
3. Confirm every required artifact id is present.
4. Confirm every artifact has path, SHA-256, capture timestamp, source, redaction status, and description.
5. Confirm READ_ONLY effective mode and disabled execution/order authority.
6. Confirm clean-start, flatten, and cancel-all workflows were disabled and not run.
7. Confirm zero submitted/cancelled/modified broker orders.
8. Confirm scanner/focus artifacts show no manual focus and no prep-seeded survivor.
9. Confirm catalyst status is explicit for every focused symbol.
10. Confirm setup/decision/risk records exist for any intent path.
11. Confirm no-trade paths persist blocker reasons without fake intents.
12. Confirm durable storage write/readback evidence exists.
13. Confirm `PAPER_READY` remains `NO` unless every objective gate passes and unresolved numeric R:R/lifecycle policy blockers are separately accepted or certified.

## PAPER Readiness Impact

PR1032 changes the readiness process, not the runtime trading system. It makes the next operational certification auditable by defining exactly what the broker-connected READ_ONLY run must produce and by adding the operator runbook needed to run it safely.

| Readiness area | PR1032 status | PAPER impact |
| --- | --- | --- |
| Operator runbook | Ready to use | Positive process contribution |
| Capture protocol | Ready to run | Positive process contribution |
| Real broker-connected artifact | Not captured | PAPER blocked |
| Operator acknowledgement artifact | Not captured | PAPER blocked |
| Zero broker order audit | Not captured | PAPER blocked |
| Durable storage readback | Not captured | PAPER blocked |
| Numeric target/R:R | Still partial from PR1030/PR1031 | PAPER blocked unless explicitly deferred or certified |
| Partial/trailing/breakeven lifecycle | Still not certified | PAPER blocked unless explicitly deferred or certified |
| PAPER/LIVE enablement | Not added | Safe |

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py
python -m pytest tests/test_ross_pr1031_readonly_full_session_paper_readiness_gate.py tests/test_ross_pr1030_entry_stop_target_exit_mapping.py tests/test_ross_pr1029_pattern_detection_certification.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1032 adds a READ_ONLY broker-connected runtime operator runbook, artifact capture pack, and manifest template. It does not certify that the broker-connected run has happened, does not enable PAPER/LIVE, and does not change production trading behavior. Ross Momentum remains `PAPER_READY: NO`.
