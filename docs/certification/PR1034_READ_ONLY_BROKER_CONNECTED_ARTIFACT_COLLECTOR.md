# PR1034 READ_ONLY Broker-Connected Artifact Collector

## Scope

PR1034 adds an operator-facing READ_ONLY broker-connected artifact collector. The collector is a narrow bridge between the PR1032 broker-connected capture contract and the PR1033 artifact validator. It can connect to IBKR only when the operator explicitly passes `--connect-ibkr-readonly` and the READ_ONLY safety environment passes.

The collector captures a broker connection and zero-order audit shell, writes PR1032-shaped raw artifacts, and then calls the PR1033 validator to redact, hash, normalize, and emit the reviewed artifact manifest.

This PR does not connect to IBKR in CI. It does not submit, cancel, modify, preview-submit, stage, flatten, reconcile, or clean-start broker state. It does not enable PAPER or LIVE. It does not certify that the full broker-connected READ_ONLY strategy observation has already happened.

## Executive Verdict

```text
PAPER_READY: NO
READ_ONLY_BROKER_CONNECTED_ARTIFACT_COLLECTOR: ADDED
COLLECTOR_REQUIRES_EXPLICIT_CONNECT_FLAG: YES
COLLECTOR_REQUIRES_READ_ONLY_ENV: YES
CI_CONNECTS_TO_IBKR: NO
SCRIPT_SUBMITS_ORDERS: NO
SCRIPT_CANCELS_OR_MODIFIES_ORDERS: NO
SCRIPT_FLATTENS_POSITIONS: NO
SCRIPT_RUNS_CLEAN_START: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PRODUCTION_TRADING_CODE_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
PAPER_LIVE_ENABLED: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Operator may run the PR1034 collector in a controlled READ_ONLY broker session, then review the PR1033-validated artifacts and fill any remaining scanner/catalyst/strategy runtime evidence gaps.
DO_NOT_GO_PAPER_REASON: PR1034 adds the broker-connected collector path only; CI does not connect to IBKR, this PR does not contain real broker-connected runtime evidence, and scanner/catalyst/full strategy session artifacts remain blockers until captured from an operator-controlled READ_ONLY session.
```

PAPER readiness remains blocked.

## PR1035 Correction Note

PR1035 tightens the collector without changing trading behavior. The corrected collector bootstraps ib_insync's asyncio support before creating the `IB()` object and fails closed if broker order/account evidence cannot be read. An open-order request/read failure, a managed-account read failure, missing broker snapshot fields, or explicit failure status rows now abort the capture before PR1032 raw artifacts are written.

## Files Added Or Updated

| File | Purpose |
| --- | --- |
| `scripts/certification/pr1034_readonly_broker_connected_artifact_collector.py` | Operator collector for a guarded READ_ONLY IBKR connection and PR1032-shaped raw artifacts. |
| `tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py` | CI tests using a scripted provider, proving safety gates, zero-order audit enforcement, runbook command coverage, and report no-overclaim language. |
| `docs/certification/PR1034_READ_ONLY_BROKER_CONNECTED_ARTIFACT_COLLECTOR.md` | Certification report for PR1034 scope and remaining blockers. |
| `docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md` | Adds the exact PR1034 broker-connected collector command. |

## Collector Behavior

| Capability | Behavior | Safety impact |
| --- | --- | --- |
| Explicit broker connection | CLI refuses to connect unless `--connect-ibkr-readonly` is provided. | Prevents accidental broker connection during local or CI use. |
| Runtime preflight | Reuses PR1033 READ_ONLY env validation before provider connection. | Fails before broker connection if mode/execution flags are unsafe. |
| ib_insync bootstrap | PR1035 prepares an asyncio event loop and calls `ib_insync.util.patchAsyncio()` before `IB()` is constructed. | Reduces operator-run connection failures caused by missing event-loop setup. |
| IBKR adapter | Uses `ib_insync.IB.connect(..., readonly=True)` only in operator-invoked CLI runs. | Requests broker read-only connection rather than order authority. |
| Order mutation audit | Requires submitted/cancelled/modified order counts to remain zero. | Blocks any bundle that indicates broker order mutation. |
| Open-order audit availability | PR1035 aborts on open-order request/read failure or failure status markers. | Prevents incomplete broker audit data from becoming validated-looking evidence. |
| Open-order snapshot check | Requires open-order snapshot before/after collection to be stable. | Detects unexpected broker state changes during the collection window. |
| Broker connection evidence | Requires connection/provenance fields and redacted account evidence. | Prevents incomplete broker snapshots from entering the artifact bundle. |
| PR1032 raw artifacts | Writes every required PR1032 artifact id to the raw output directory. | Keeps the artifact set machine-reviewable. |
| PR1033 validation | Calls the PR1033 validator to redact, hash, and normalize artifacts. | Reuses existing artifact review contract. |
| Strategy artifacts | Scanner/catalyst/setup/risk/storage artifacts are marked collector-only with explicit blockers. | Avoids treating broker connection as full strategy runtime proof. |

## Operator Command

The PR1032 runbook now includes the exact command. The operator must set safe READ_ONLY environment variables before running it:

```powershell
.\.venv\Scripts\python.exe scripts\certification\pr1034_readonly_broker_connected_artifact_collector.py `
  --connect-ibkr-readonly `
  --raw-output-dir artifacts\certification\pr1034\raw_readonly_broker_collect `
  --validated-output-dir artifacts\certification\pr1034\validated_readonly_broker_collect `
  --operator NELZON `
  --host 127.0.0.1 `
  --port 7497 `
  --client-id 1034
```

PR1034 collector output is not PAPER readiness evidence by itself. It proves only the collector path and the broker connection/order-audit shell captured by the operator run.

## Hard Failure Conditions

The collector aborts if any of these are true:

1. `--connect-ibkr-readonly` is absent.
2. Effective mode is not READ_ONLY.
3. Execution authority, IBKR write authority, order submission, replay mode, or clean-start is enabled.
4. ib_insync event-loop bootstrap fails.
5. The provider cannot prove `connected=true`.
6. Required broker snapshot fields are missing or malformed.
7. Managed-account read fails before redacted account evidence can be produced.
8. Submitted/cancelled/modified order counts are nonzero.
9. Open-order request or read fails.
10. Open-order audit rows contain failure, error, unavailable, or unknown status markers.
11. Open-order snapshots change during the collector window.
12. Raw and validated output directories are the same resolved path.
13. PR1033 validation fails.

## Remaining Blockers

| Blocker | Status after PR1034/PR1035 |
| --- | --- |
| Real operator-run broker-connected artifact bundle | Not captured by this PR |
| Full scanner/watchlist/focus runtime evidence | Not captured by this PR |
| Catalyst/news runtime evidence | Not captured by this PR |
| Setup/decision/risk runtime evidence | Not captured by this PR |
| Durable storage write/readback from real session | Not captured by this PR |
| Numeric target/R:R certification | Still partial from prior PRs |
| Partial/trailing/breakeven lifecycle certification | Not certified |
| PAPER readiness | `NO` |

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py
python -m pytest tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact or broker"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1034 adds a guarded READ_ONLY broker-connected collector path, and PR1035 tightens the collector's bootstrap and fail-closed broker evidence checks. It does not mutate broker state, does not connect to IBKR in CI, does not enable PAPER/LIVE, and does not certify that the real broker-connected full strategy capture has already happened. Ross Momentum remains `PAPER_READY: NO`.
