# PR1036 PR1034 Collector ib_insync Import-Order Bootstrap Fix

## Scope

PR1036 is a narrow follow-up to PR1035 for the PR1034 READ_ONLY broker-connected artifact collector. PR1035 added an ib_insync event-loop bootstrap before `IB()` construction, but the PR1036 correction requires an asyncio event loop to exist before any `ib_insync` import occurs. The corrected collector now creates or confirms that plain asyncio loop first, then imports the `IB` symbol directly.

PR1037 corrects the PR1036 audit wording and test contract: the collector does not call `patchAsyncio()` or install a default `nest_asyncio` path. The import-order certification is the plain event-loop-before-`IB` contract, not a util-patching contract.

This PR does not enable PAPER or LIVE, does not connect to IBKR in CI, does not submit/cancel/modify orders, and does not change Ross strategy thresholds or gates.

## Executive Verdict

```text
PAPER_READY: NO
PR1034_IB_INSYNC_IMPORT_ORDER_BOOTSTRAP_FIXED: YES
ASYNCIO_EVENT_LOOP_BEFORE_IB_INSYNC_IMPORT: YES
DEFAULT_PATCH_ASYNCIO_NEST_ASYNCIO_PATH_ENABLED: NO
IB_SYMBOL_LOAD_AFTER_PLAIN_EVENT_LOOP_BOOTSTRAP: YES
PR1034_FAIL_CLOSED_BROKER_EVIDENCE_PRESERVED: YES
CI_CONNECTS_TO_IBKR: NO
ORDER_MUTATION_ALLOWED: NO
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Operator must run the corrected collector in a controlled READ_ONLY broker session and review PR1033-validated artifacts before any readiness claim.
DO_NOT_GO_PAPER_REASON: PR1036 fixes collector asyncio/import ordering only; it does not provide broker-connected runtime evidence, full scanner/catalyst/session evidence, or lifecycle readiness proof.
```

Broker-connected runtime artifact captured by this PR: NO.

## Fix Detail

The collector creates or confirms an asyncio event loop before any `ib_insync` import. After that plain-loop bootstrap, it imports `IB`, instantiates `IB()`, and connects with `readonly=True`.

The collector does not call `patchAsyncio()` or install a default `nest_asyncio` path. Any future decision to add an async patching mode should be explicit, separately reviewed, and fail closed.

| Area | Before PR1036 correction | After PR1036/PR1037 correction | Status |
| --- | --- | --- | --- |
| Asyncio event loop | The loop was not guaranteed before the ib_insync import path. | The loop is created or confirmed before any `ib_insync` import. | FIXED |
| ib_insync import order | `IB` could be loaded before a current event loop existed. | `ensure_asyncio_event_loop()` runs first, then `IB` is imported. | FIXED |
| Default async patching | Earlier audit wording described a default `util.patchAsyncio()` path. | No default `patchAsyncio()` or `nest_asyncio` path is used. | REMOVED |
| Event-loop bootstrap | Happened before `IB()` construction but not before all `ib_insync` imports. | Happens before any `ib_insync` import and before `IB()` construction. | TIGHTENED |
| Fail-closed broker audit | PR1035 fail-closed behavior was present. | PR1035 fail-closed behavior is preserved. | PRESERVED |
| CI broker behavior | CI used fake providers/modules and did not connect to IBKR. | CI still uses fake providers/modules and does not connect to IBKR. | PRESERVED |

## Safety Boundary

| Safety item | PR1036 status |
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

`tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py` covers:

1. Asyncio event loop setup happens before the `IB` symbol is loaded.
2. The collector does not access `ib_insync.util`, call `patchAsyncio()`, or install a default `nest_asyncio` path.
3. The provider still connects with `readonly=True` using a fake ib_insync module only.
4. Missing `IB` after plain loop bootstrap aborts as `CollectorValidationError`.
5. This report keeps `PAPER_READY: NO`, `PAPER_READINESS_GATE: FAIL`, and `DEFAULT_PATCH_ASYNCIO_NEST_ASYNCIO_PATH_ENABLED: NO`.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact or broker"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions remains the authoritative verification surface for this PR.

## Final Certification Answer

PR1036 corrects the PR1034 collector's asyncio and ib_insync import ordering while preserving PR1035 fail-closed broker evidence behavior. PR1037 clarifies that this is a plain-loop-before-`IB` contract, not a default `patchAsyncio()`/`nest_asyncio` contract. It does not add broker-connected runtime evidence, does not run IBKR in CI, does not enable PAPER/LIVE, and does not mutate broker state. Ross Momentum remains `PAPER_READY: NO`.
