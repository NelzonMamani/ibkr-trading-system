# PR1032 READ_ONLY Broker-Connected Runtime Artifact Capture Pack

## Scope

PR1032 provides the artifact capture pack required after PR1031. It defines the evidence bundle that must be captured during a future broker-connected READ_ONLY runtime session before any PAPER enablement decision can be considered.

This PR does not certify that a broker-connected session has already completed. It creates a strict capture contract, manifest template, acceptance gates, rejection conditions, and review checklist for the future run.

No PAPER/LIVE enablement was added. No production trading behavior was changed. No trading thresholds were changed. No Ross scanner, float, RVOL, gap, catalyst, setup, decision, risk, mapping, or execution rule was weakened. No fake numeric targets, fake R:R, fake partials, fake trailing, fake lifecycle evidence, or fake broker orders were added.

## Executive Verdict

```text
PAPER_READY: NO
BROKER_CONNECTED_READ_ONLY_ARTIFACT_CAPTURE_PACK: READY_TO_RUN
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED: NO
BROKER_ORDER_AUDIT_CAPTURED: NO
DURABLE_STORAGE_READBACK_CAPTURED: NO
PAPER_READINESS_GATE: FAIL
PRODUCTION_CODE_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
PAPER_LIVE_ENABLED: NO
NEXT_REQUIRED_ACTION: Run a real broker-connected READ_ONLY session using this capture pack, redact/hash the artifact bundle, and review every acceptance gate before any PAPER decision.
DO_NOT_GO_PAPER_REASON: PR1032 only prepares the broker-connected READ_ONLY artifact capture pack; it does not contain captured broker runtime evidence, zero-order broker audit proof, durable storage readback proof, numeric R:R certification, or partial/trailing/breakeven lifecycle certification.
```

PAPER readiness remains blocked. The capture pack is ready to run, but a real broker-connected READ_ONLY session artifact has not been captured by this PR.

## Capture Pack Contents

| File | Purpose | Status |
| --- | --- | --- |
| `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json` | Machine-readable manifest template for the future broker-connected READ_ONLY artifact bundle. | Added |
| `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_CAPTURE_PACK.md` | Human-readable capture protocol, evidence matrix, rejection rules, and readiness verdict. | Added |
| `tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py` | Regression tests that pin the capture-pack contract and prevent PAPER-readiness overclaiming. | Added |

## Required Operator Run Constraints

The future artifact capture run must satisfy all of these constraints before it can be reviewed:

| Constraint | Required value | Failure condition |
| --- | --- | --- |
| `RUN_MODE_EFFECTIVE` | `READ_ONLY` | Any `PAPER` or `LIVE` effective mode. |
| `EXECUTION_ENABLED_EFFECTIVE` | `false` | `true` or missing value. |
| `EVENT_REPLAY_MODE_EFFECTIVE` | `OFF` | Any replay mode active in the broker-connected run. |
| IBKR API write access | `false` | API write access enabled. |
| IBKR order submission | `false` | Order submission enabled. |
| Broker order mutations | `0 submitted`, `0 cancelled`, `0 modified` | Any broker order mutation. |
| Artifact redaction | Account/secrets redacted or absent | Unredacted account id, token, credential, host secret, or session secret. |
| Artifact hashing | SHA-256 for every file | Missing hash or changed file after review. |

## Required Artifact Bundle

| Artifact id | Required evidence | Must prove | Status in this PR |
| --- | --- | --- | --- |
| `runtime_config_snapshot` | Runtime mode/effective mode, execution flags, event replay mode, IBKR write/order flags. | READ_ONLY, execution disabled, replay OFF. | Template only |
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

## Acceptance Gates

| Gate | Required pass condition | Current PR1032 result |
| --- | --- | --- |
| READ_ONLY mode only | Runtime artifact proves effective mode is READ_ONLY. | Not captured |
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

1. `RUN_MODE_EFFECTIVE=PAPER` or `RUN_MODE_EFFECTIVE=LIVE`.
2. `EXECUTION_ENABLED_EFFECTIVE=true`.
3. `IBKR_ORDER_SUBMISSION_ENABLED=true` or equivalent order submission authority.
4. Any submitted, cancelled, or modified broker order.
5. Any synthetic broker order, fake trade, fake lifecycle event, or fabricated storage record.
6. Missing runtime config snapshot.
7. Missing broker order audit.
8. Missing durable storage readback evidence.
9. Missing scanner/watchlist/focus artifact.
10. Missing setup/decision/risk artifact for an intent path.
11. Unredacted account id, token, credential, or session secret.
12. Missing SHA-256 hash for any artifact file.

## Review Checklist For The Future Broker-Connected Run

1. Confirm artifact bundle uses the PR1032 manifest schema.
2. Confirm every required artifact id is present.
3. Confirm every artifact has path, SHA-256, capture timestamp, source, redaction status, and description.
4. Confirm READ_ONLY effective mode and disabled execution/order authority.
5. Confirm zero submitted/cancelled/modified broker orders.
6. Confirm scanner/focus artifacts show no manual focus and no prep-seeded survivor.
7. Confirm catalyst status is explicit for every focused symbol.
8. Confirm setup/decision/risk records exist for any intent path.
9. Confirm no-trade paths persist blocker reasons without fake intents.
10. Confirm durable storage write/readback evidence exists.
11. Confirm `PAPER_READY` remains `NO` unless every objective gate passes and unresolved numeric R:R/lifecycle policy blockers are separately accepted or certified.

## PAPER Readiness Impact

PR1032 changes the readiness process, not the runtime trading system. It makes the next operational certification auditable by defining exactly what the broker-connected READ_ONLY run must produce.

| Readiness area | PR1032 status | PAPER impact |
| --- | --- | --- |
| Capture protocol | Ready to run | Positive process contribution |
| Real broker-connected artifact | Not captured | PAPER blocked |
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

PR1032 adds a READ_ONLY broker-connected runtime artifact capture pack and manifest template. It does not certify that the broker-connected run has happened, does not enable PAPER/LIVE, and does not change production trading behavior. Ross Momentum remains `PAPER_READY: NO`.
