# PR1036 PR1034 Collector ib_insync Import-Order Bootstrap Fix

## Scope

PR1036 is a narrow follow-up to PR1035 for the PR1034 READ_ONLY broker-connected artifact collector. PR1035 added an ib_insync event-loop bootstrap before `IB()` construction, but the import statement still requested `IB` and `util` together. PR1036 separates that sequence so the collector loads `ib_insync.util`, completes bootstrap, and only then loads the `IB` symbol.

This PR does not enable PAPER or LIVE, does not connect to IBKR in CI, does not submit/cancel/modify orders, and does not change Ross strategy thresholds or gates.

## Executive Verdict

```text
PAPER_READY: NO
PR1034_IB_INSYNC_IMPORT_ORDER_BOOTSTRAP_FIXED: YES
UTIL_BOOTSTRAP_BEFORE_IB_SYMBOL_LOAD: YES
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
DO_NOT_GO_PAPER_REASON: PR1036 fixes collector import/bootstrap ordering only; it does not provide broker-connected runtime evidence, full scanner/catalyst/session evidence, or lifecycle readiness proof.
```

Broker-connected runtime artifact captured by this PR: NO.

## Fix Detail

The collector imports `ib_insync.util` and completes event-loop bootstrap before importing or instantiating `IB`.

| Area | Before PR1036 | After PR1036 | Status |
| --- | --- | --- | --- |
| ib_insync import order | `IB` and `util` were requested in one import statement. | `util` is requested first, `bootstrap_ib_insync_event_loop(util)` runs, then `IB` is requested. | FIXED |
| Event-loop bootstrap | Happened before `IB()` construction but not before the `IB` symbol was requested. | Happens before the collector imports or instantiates `IB`. | TIGHTENED |
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
| PAPER readiness | NO |

## Tests Added

`tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py` covers:

1. `ib_insync.util` is accessed and patched before the `IB` symbol is accessed.
2. The provider still connects with `readonly=True` using a fake ib_insync module only.
3. Missing `IB` after util bootstrap aborts as `CollectorValidationError`.
4. This report keeps `PAPER_READY: NO` and `PAPER_READINESS_GATE: FAIL`.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact or broker"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions remains the authoritative verification surface for this PR.

## Final Certification Answer

PR1036 corrects the PR1034 collector's ib_insync import/bootstrap ordering while preserving PR1035 fail-closed broker evidence behavior. It does not add broker-connected runtime evidence, does not run IBKR in CI, does not enable PAPER/LIVE, and does not mutate broker state. Ross Momentum remains `PAPER_READY: NO`.
