# PR1035 PR1034 ib_insync Event-Loop And Fail-Closed Broker Collector Fix

## Scope

PR1035 is a narrow correction to the PR1034 READ_ONLY broker-connected artifact collector. It fixes the ib_insync connection bootstrap path and tightens broker evidence handling so incomplete broker audit data aborts capture instead of becoming validated-looking artifact data.

This PR does not enable PAPER or LIVE, does not submit/cancel/modify orders, does not connect to IBKR in CI, and does not change Ross strategy thresholds or gates.

## Executive Verdict

```text
PAPER_READY: NO
PR1034_EVENT_LOOP_BOOTSTRAP_FIXED: YES
PR1034_FAIL_CLOSED_BROKER_EVIDENCE: YES
OPEN_ORDER_REQUEST_FAILURE_ABORTS_CAPTURE: YES
OPEN_ORDER_READ_FAILURE_ABORTS_CAPTURE: YES
MANAGED_ACCOUNT_READ_FAILURE_ABORTS_CAPTURE: YES
CI_CONNECTS_TO_IBKR: NO
ORDER_MUTATION_ALLOWED: NO
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Operator must rerun the corrected collector in a controlled READ_ONLY broker session and review PR1033-validated artifacts before any readiness claim.
DO_NOT_GO_PAPER_REASON: PR1035 fixes collector safety mechanics only; it does not provide real broker-connected runtime evidence, full scanner/catalyst/session evidence, or lifecycle readiness proof.
```

Broker-connected runtime artifact captured by this PR: NO.

## Fix Matrix

| Area | Previous behavior | PR1035 behavior | Certification result |
| --- | --- | --- | --- |
| ib_insync event-loop bootstrap | `IB()` was created without an explicit event-loop/bootstrap step. | `bootstrap_ib_insync_event_loop()` prepares an asyncio loop and calls `ib_insync.util.patchAsyncio()` before `IB()` is constructed. | FIXED |
| Open-order request failure | `reqOpenOrders()` exceptions were recorded as a row with `OPEN_ORDER_REQUEST_FAILED`. | Any request exception raises `CollectorValidationError` and aborts capture. | FAIL-CLOSED |
| Open-order read failure | `openOrders()` failures were not separately guarded. | Any read exception raises `CollectorValidationError` and aborts capture. | FAIL-CLOSED |
| Managed account read failure | Account lookup failures silently produced `NO_SECRET_DATA_PRESENT`. | Account lookup exceptions abort capture because broker/redaction evidence is incomplete. | FAIL-CLOSED |
| Broker snapshot schema | Snapshot validation focused on connected flag, zero mutation counts, and stable open-order snapshots. | Snapshot validation also requires connection/provenance fields, list-shaped open-order rows, and no failure/error status markers. | TIGHTENED |
| Raw/validated output dirs | Compared direct `Path` objects only. | Compares resolved paths so equivalent paths cannot reuse the same output location. | TIGHTENED |

## Fail-Closed Broker Evidence Rules

The corrected collector aborts before writing PR1032 raw artifacts if any of these broker evidence checks fail:

1. ib_insync event-loop bootstrap raises an exception.
2. IBKR open-order request cannot be completed.
3. IBKR open-order rows cannot be read.
4. Managed account lookup fails before redacted account evidence can be produced.
5. Broker snapshot is missing required connection fields.
6. Submitted, cancelled, or modified order counts are nonzero.
7. Open-order before/after snapshots differ.
8. Open-order audit rows contain failure/error/unavailable status markers.

These rules preserve the zero-order, READ_ONLY artifact contract. They do not grant execution authority.

## Safety Boundary

| Safety item | PR1035 status |
| --- | --- |
| Production trading behavior changed | NO |
| Ross thresholds changed | NO |
| Ross gates weakened | NO |
| PAPER enabled | NO |
| LIVE enabled | NO |
| CI broker connection | NO |
| Broker order submission | NO |
| Broker order cancellation | NO |
| Broker order modification | NO |
| Position flattening | NO |
| Clean-start behavior | NO |
| PAPER readiness | NO |

## Tests Added

`tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py` covers:

1. ib_insync event-loop bootstrap runs before the `IB()` object is created.
2. Bootstrap failure aborts connection setup.
3. Open-order request failure aborts capture.
4. Open-order read failure aborts capture.
5. Managed account read failure aborts capture.
6. Failure marker rows in broker order audit are rejected even if before/after snapshots are stable.
7. Broker snapshot evidence must contain required connection/redaction fields.
8. This report keeps `PAPER_READY: NO` and `PAPER_READINESS_GATE: FAIL`.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py
python -m pytest tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact or broker"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions remains the authoritative verification surface for this PR.

## Final Certification Answer

PR1035 corrects the PR1034 collector bootstrap and fail-closed broker evidence behavior. It does not add broker-connected runtime evidence, does not run IBKR in CI, does not enable PAPER/LIVE, and does not mutate broker state. Ross Momentum remains `PAPER_READY: NO`.
