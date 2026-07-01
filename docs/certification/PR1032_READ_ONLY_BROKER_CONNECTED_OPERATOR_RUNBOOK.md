# PR1032 READ_ONLY Broker-Connected Operator Runbook

## Purpose

This runbook gives the operator steps for the future broker-connected READ_ONLY capture run required by PR1032. It is not captured evidence by itself. It tells the operator how to prepare, run, stop, redact, hash, and review the artifact bundle without enabling PAPER or LIVE and without allowing broker order mutation.

Use this runbook together with:

- `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json`
- `docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_CAPTURE_PACK.md`

## Executive Safety Rule

```text
PAPER_READY: NO
RUNBOOK_STATUS: READY_FOR_FUTURE_OPERATOR_RUN
RUNBOOK_CAPTURED_ARTIFACT_STATUS: NOT_CAPTURED
ALLOWED_MODE: READ_ONLY
FORBIDDEN_MODES: PAPER,LIVE
ORDER_MUTATION_ALLOWED: NO
CLEAN_START_ALLOWED: NO
PAPER_LIVE_ENABLEMENT_ALLOWED: NO
```

Stop immediately if any runtime surface reports PAPER, LIVE, executable order authority, clean-start behavior, order submission, order cancellation, order modification, or an unredacted secret/account identifier.

## Pre-Run Checklist

Complete this checklist before connecting to a broker session.

| Check | Required value | Abort if |
| --- | --- | --- |
| Operator intent | READ_ONLY artifact capture only | Any intent to test PAPER/LIVE trading |
| `RUN_MODE` | `READ_ONLY` | `PAPER`, `LIVE`, or empty/unknown |
| `RUN_MODE_EFFECTIVE` | `READ_ONLY` | `PAPER`, `LIVE`, or empty/unknown |
| `EXECUTION_ENABLED` | `false` | `true` |
| `EXECUTION_ENABLED_EFFECTIVE` | `false` | `true` |
| `EVENT_REPLAY_MODE_EFFECTIVE` | `OFF` | Any replay mode active during broker-connected run |
| `IBKR_API_WRITE_ALLOWED` | `false` | `true` |
| `IBKR_ORDER_SUBMISSION_ENABLED` | `false` | `true` |
| `FORCE_CLEAN_START` | `false` | `true` |
| `FORCE_EXECUTION_ON_TRADE_READY` | `false` or absent | `true` |
| `FORCE_RISK_APPROVAL_FOR_TRADE_READY` | `false` or absent | `true` |
| `VALIDATION_SESSION_OVERRIDE` | `false` or absent | `true` outside explicit validation-only replay |
| `ALLOW_PAPER_AFTER_HOURS_INTENTS` | `false` or absent | `true` |
| Manual focus | Disabled or absent | Any manually injected operational focus list |
| Synthetic intent path | Disabled or absent | Any synthetic/fake intent source enabled |
| Broker account display | Redaction plan ready | Account id will be stored unredacted |
| Output directory | Fresh empty artifact directory | Directory contains stale artifacts from another run |

## Required Artifact Directory

Create a fresh artifact directory for the future run. The directory name should include the PR id, run date, and mode, for example:

```text
artifacts/certification/pr1032/YYYYMMDD_READ_ONLY_broker_capture/
```

The directory must contain no stale files before the run starts. Do not reuse a previous failed run directory. If a run aborts, keep the aborted directory and create a new one for the next attempt.

## PR1033 Artifact Validator / Dry-Run Commands

Run this before the future broker-connected capture to verify that the PR1033 artifact validator, READ_ONLY safety preflight, redaction, hashing, and manifest-writing path are available locally. This does not connect to IBKR and does not validate real broker artifacts.

```powershell
cd "C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system"

git status
git branch --show-current
git pull --ff-only origin main

$env:RUN_MODE="READ_ONLY"
$env:RUN_MODE_EFFECTIVE="READ_ONLY"
$env:EXECUTION_ENABLED="false"
$env:EXECUTION_ENABLED_EFFECTIVE="false"
$env:EVENT_REPLAY_MODE="OFF"
$env:EVENT_REPLAY_MODE_EFFECTIVE="OFF"
$env:IBKR_API_WRITE_ALLOWED="false"
$env:IBKR_ORDER_SUBMISSION_ENABLED="false"
$env:FORCE_CLEAN_START="false"

.\.venv\Scripts\python.exe scripts\certification\pr1033_readonly_broker_artifact_capture.py `
  --dry-run `
  --output-dir artifacts\certification\pr1033\dry_run_readonly_capture `
  --operator NELZON
```

Dry-run output is not broker-connected evidence. It only proves the PR1033 validator can run locally, enforce READ_ONLY environment gates, write placeholder schema artifacts, hash/redact outputs, and keep `PAPER_READY=NO`.

## Required Artifacts To Capture

The future broker-connected run must produce these files or equivalent redacted artifacts. File names may vary, but each artifact id must map to one captured file in the manifest.

| Artifact id | Example file | Required content |
| --- | --- | --- |
| `operator_runbook_acknowledgement` | `operator_runbook_acknowledgement.json` | Operator, timestamp, runbook path, safety checklist result, explicit `PAPER_READY=NO`. |
| `runtime_config_snapshot` | `runtime_config_snapshot.json` | Mode, effective mode, execution flags, replay mode, IBKR write/order flags, clean-start flags. |
| `broker_connection_snapshot` | `broker_connection_snapshot.json` | Connected status, host/port/client id, market data type, redacted account id. |
| `scanner_cycle_artifact` | `scanner_cycle_artifact.json` | Provider source, scanner contract, top-N, drop ledger, selection spec. |
| `catalyst_news_artifact` | `catalyst_news_artifact.json` | News source mode, as-of time, catalyst status by symbol, fresh/stale counts. |
| `watchlist_focus_artifact` | `watchlist_focus_artifact.json` | Watchlist K, focus M, row-level provenance, no manual/prep survivor proof. |
| `pattern_input_artifact` | `pattern_input_artifact.json` | Timeframe provenance, data quality flags, liquidity, levels, indicators, news context. |
| `setup_decision_artifact` | `setup_decision_artifact.json` | Detected setups, selected setup, entry/stop/target model, rationale, decision reason. |
| `risk_gate_artifact` | `risk_gate_artifact.json` | Risk called/approved flags, reason, risk profile, vetoes. |
| `execution_gate_artifact` | `execution_gate_artifact.json` | Execution enabled false, order submission false, API write false, order attempts zero. |
| `broker_order_audit` | `broker_order_audit.json` | Submitted/cancelled/modified order counts, open orders before/after. |
| `analytics_storage_artifact` | `analytics_storage_artifact.json` | Storage writes, readbacks, trade-plan records, no-trade records, artifact paths. |
| `final_verdict` | `final_verdict.json` | PAPER verdict, blockers, acceptance gate result, operator signature. |

## Operator Sequence

Follow these steps in order.

1. Confirm the PR1032 manifest schema and this runbook are present in the checkout.
2. Create a fresh artifact directory.
3. Capture the pre-run runtime config snapshot.
4. Confirm all pre-run checklist values are safe.
5. Connect to broker market data in READ_ONLY mode only.
6. Capture the broker connection snapshot with account id redacted.
7. Run exactly one controlled READ_ONLY observation session long enough to produce scanner/watchlist/focus and decision artifacts.
8. Do not submit, cancel, modify, preview-submit, or stage broker orders.
9. Do not run clean-start, flatten, cancel-all, or position-reconciliation mutation workflows.
10. Capture scanner, catalyst/news, watchlist/focus, pattern input, setup/decision, risk, execution gate, order audit, analytics/storage, and final verdict artifacts.
11. Redact all account identifiers, host secrets, credentials, tokens, and session secrets.
12. Compute SHA-256 for every artifact file after redaction.
13. Populate the PR1032 manifest from the example template using only captured, redacted, hashed files.
14. Review every acceptance gate.
15. Keep `PAPER_READY=NO` unless every objective gate passes and any remaining numeric R:R or lifecycle blockers are separately resolved.

## Immediate Abort Conditions

Abort the run and preserve the partial artifact directory if any of these occur:

1. Effective mode resolves to `PAPER` or `LIVE`.
2. Execution enabled resolves to `true`.
3. IBKR API write access resolves to `true`.
4. IBKR order submission resolves to `true`.
5. Clean-start, cancel-all, flatten, or order reconciliation mutation workflow starts.
6. Any broker order is submitted, cancelled, modified, preview-submitted, or staged.
7. Any fake trade, synthetic broker order, or fabricated lifecycle event appears.
8. Scanner/focus artifacts are missing or sourced from manual focus/prep seed.
9. Catalyst status is unavailable for a focused symbol without a persisted blocker.
10. Storage write/readback cannot be captured.
11. A required artifact contains unredacted account id, token, credential, or secret.
12. Any artifact cannot be hashed after redaction.

## Post-Run Validation

After the run, verify:

| Validation | Required outcome |
| --- | --- |
| Manifest schema | `PR1032.readonly_broker_runtime_artifact.v1` |
| Runtime mode | `READ_ONLY` only |
| Execution authority | Disabled |
| Order audit | Submitted/cancelled/modified counts all zero |
| Scanner/focus | No manual focus, no prep-seeded survivor |
| Catalyst/news | Explicit status for each focused symbol |
| Decision/risk | Every intent has decision and risk evidence; no-trade paths have blockers |
| Execution gate | Order attempts zero |
| Storage | Write/readback evidence present |
| Redaction | Account/secrets redacted or verified absent |
| Hashing | SHA-256 present for every artifact |
| Final verdict | `PAPER_READY=NO` unless every objective gate passes |

## Final Operator Certification Block

The future operator must fill this block in the captured `final_verdict` artifact.

```text
RUNBOOK_USED: PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md
RUN_MODE_EFFECTIVE: READ_ONLY
EXECUTION_ENABLED_EFFECTIVE: false
IBKR_API_WRITE_ALLOWED: false
IBKR_ORDER_SUBMISSION_ENABLED: false
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED: YES/NO
SUBMITTED_ORDERS_COUNT: 0
CANCELLED_ORDERS_COUNT: 0
MODIFIED_ORDERS_COUNT: 0
DURABLE_STORAGE_READBACK_CAPTURED: YES/NO
ARTIFACTS_REDACTED: YES/NO
ARTIFACTS_HASHED: YES/NO
PAPER_READY: NO
OPERATOR_SIGNATURE: <name-or-initials>
CAPTURED_AT_UTC: <timestamp>
```

If any value is unknown, missing, unsafe, or nonzero where zero is required, the final verdict must remain `PAPER_READY: NO` and the broker-connected runtime artifact must not be certified.
