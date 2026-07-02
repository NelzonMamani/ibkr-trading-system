# PR1037 PR1034 Collector Python 3.14 ib_insync Connect Timeout Fix

## Scope

PR1037 is a narrow follow-up to the PR1034 READ_ONLY broker-connected artifact collector. PR1036 fixed asyncio and ib_insync import/bootstrap ordering. PR1037 fixes the next fail-closed boundary: if the Python 3.14/ib_insync connect timeout path raises during `IB.connect(...)`, the collector now aborts cleanly as `CollectorValidationError`, disconnects the partially created IB object, and does not proceed to broker audit or artifact writing.

This correction also removes the default `patchAsyncio()`/`nest_asyncio` route. The collector now creates or confirms a plain asyncio event loop before importing `ib_insync.IB`; it does not import `ib_insync.util` by default and does not install an async patching layer as part of the operator collector path.

This PR does not enable PAPER or LIVE, does not connect to IBKR in CI, does not submit/cancel/modify orders, and does not change Ross strategy thresholds or gates.

## Executive Verdict

```text
PAPER_READY: NO
PR1034_IB_INSYNC_CONNECT_TIMEOUT_FAILS_CLOSED: YES
PYTHON314_CONNECT_TIMEOUT_PATH_GUARDED: YES
PARTIAL_IB_OBJECT_DISCONNECTED_ON_CONNECT_FAILURE: YES
PR1036_ASYNCIO_IMPORT_BOOTSTRAP_PRESERVED: YES
DEFAULT_PATCH_ASYNCIO_NEST_ASYNCIO_PATH_ENABLED: NO
PR1035_FAIL_CLOSED_BROKER_EVIDENCE_PRESERVED: YES
CI_CONNECTS_TO_IBKR: NO
ORDER_MUTATION_ALLOWED: NO
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Operator must run the corrected collector in a controlled READ_ONLY broker session and review PR1033-validated artifacts before any readiness claim.
DO_NOT_GO_PAPER_REASON: PR1037 fixes collector connect-timeout error handling and removes default asyncio patching only; it does not provide broker-connected runtime evidence, full scanner/catalyst/session evidence, or lifecycle readiness proof.
```

Broker-connected runtime artifact captured by this PR: NO.

## Fix Detail

Connect timeout exceptions now abort as `CollectorValidationError` before broker audit begins. The collector disconnects the partially created IB object before raising so the operator sees a controlled PR1034 abort instead of a raw timeout stack escaping the CLI.

The default `patchAsyncio()`/`nest_asyncio` route is not used. The collector preserves the PR1036 intent by creating or confirming a plain asyncio event loop before importing the `IB` symbol, then it instantiates `IB()` and connects with `readonly=True`.

| Area | Before PR1037 correction | After PR1037 correction | Status |
| --- | --- | --- | --- |
| `IB.connect(...)` timeout | A timeout could escape as a raw Python/ib_insync exception. | Timeout is converted to `CollectorValidationError` with a clear READ_ONLY abort reason. | FIXED |
| Partial IB object cleanup | A partially created IB object might be left to caller/runtime cleanup. | The collector calls `disconnect()` after connect failure and preserves the original failure reason. | FAIL-CLOSED |
| Generic connect failure | Non-timeout connect exceptions could escape the PR1034 abort path. | Non-timeout connect exceptions also become `CollectorValidationError`. | FAIL-CLOSED |
| PR1036 bootstrap | Asyncio loop before `ib_insync` import was present. | Plain asyncio loop is created or confirmed before importing `IB`. | PRESERVED |
| Default async patching | The branch could call `ib_insync.util.patchAsyncio()` by default. | The collector does not call `patchAsyncio()` or install `nest_asyncio` by default. | REMOVED |
| PR1035 broker audit guards | Open-order/account/snapshot fail-closed rules were present. | Preserved. | PRESERVED |
| CI broker behavior | CI used fake providers/modules and did not connect to IBKR. | CI still uses fake providers/modules and does not connect to IBKR. | PRESERVED |

## Safety Boundary

| Safety item | PR1037 status |
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
| Default `patchAsyncio()`/`nest_asyncio` route | NO |
| PAPER readiness | NO |

## Tests Added Or Updated

`tests/test_ross_pr1037_pr1034_ib_insync_connect_timeout.py` covers:

1. A simulated Python 3.14/ib_insync connect timeout raises `CollectorValidationError`.
2. The collector disconnects the partially created fake IB object after connect timeout.
3. The collector still passes `readonly=True` and the configured timeout into `IB.connect(...)`.
4. Generic connect failures fail closed and disconnect.
5. Disconnect cleanup errors do not hide the original connect failure.
6. Fake `ib_insync` modules fail the test if the default `util.patchAsyncio()` route is touched.
7. This report keeps `PAPER_READY: NO`, `PAPER_READINESS_GATE: FAIL`, and `DEFAULT_PATCH_ASYNCIO_NEST_ASYNCIO_PATH_ENABLED: NO`.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1037_pr1034_ib_insync_connect_timeout.py
python -m pytest tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact or broker"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions remains the authoritative verification surface for this PR.

## Final Certification Answer

PR1037 fixes the PR1034 collector's Python 3.14/ib_insync connect timeout path while preserving PR1036 plain asyncio/import ordering and PR1035 fail-closed broker evidence behavior. It removes the default `patchAsyncio()`/`nest_asyncio` path, does not add broker-connected runtime evidence, does not run IBKR in CI, does not enable PAPER/LIVE, and does not mutate broker state. Ross Momentum remains `PAPER_READY: NO`.
