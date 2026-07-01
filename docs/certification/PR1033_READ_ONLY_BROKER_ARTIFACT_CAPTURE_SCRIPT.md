# PR1033 READ_ONLY Broker Artifact Capture Script

## Scope

PR1033 adds the READ_ONLY broker artifact capture script that operationalizes the PR1032 runbook and manifest contract. The script assembles and validates operator-provided JSON artifacts from a future broker-connected READ_ONLY run, redacts secret-like fields, computes SHA-256 hashes, writes normalized artifact copies, and emits a review manifest.

PR1033 also adds a `--dry-run` mode. Dry-run mode generates placeholder artifacts to prove the validator path, READ_ONLY safety preflight, redaction, hashing, and manifest writing locally. Dry-run output is not broker-connected evidence and must not be used to certify PAPER readiness.

This PR does not connect to IBKR. It does not submit, cancel, modify, preview-submit, stage, flatten, or reconcile broker orders. It does not enable PAPER or LIVE. It does not certify that a broker-connected session has already happened.

## Executive Verdict

```text
PAPER_READY: NO
READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT: ADDED
DRY_RUN_SUPPORTED: YES
DRY_RUN_STATUS: DRY_RUN_VALIDATED_NOT_BROKER_EVIDENCE
SCRIPT_CONNECTS_TO_BROKER: NO
SCRIPT_SUBMITS_ORDERS: NO
SCRIPT_CANCELS_OR_MODIFIES_ORDERS: NO
SCRIPT_FLATTENS_POSITIONS: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PRODUCTION_TRADING_CODE_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
PAPER_LIVE_ENABLED: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Run the PR1033 dry-run locally, then use the PR1033 script during a future operator-controlled READ_ONLY broker artifact capture run with real, redacted, hashable artifacts.
DO_NOT_GO_PAPER_REASON: PR1033 adds offline artifact capture tooling and dry-run validation only; it does not contain real broker-connected runtime evidence, zero-order broker audit proof from a live session, durable storage readback proof from a live session, numeric R:R certification, or partial/trailing/breakeven lifecycle certification.
```

PAPER readiness remains blocked.

## Files Added Or Updated

| File | Purpose |
| --- | --- |
| `scripts/certification/pr1033_readonly_broker_artifact_capture.py` | Offline READ_ONLY artifact validator/assembler with `--dry-run` support. |
| `tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py` | Tests for safe env enforcement, complete artifact contract, dry-run output, redaction, hashing, runbook command coverage, and no-overclaim report language. |
| `docs/certification/PR1033_READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT.md` | Certification report for PR1033 scope and remaining blockers. |
| `docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md` | Adds the exact PR1033 artifact validator dry-run command block for the operator. |

## Script Behavior

| Capability | Behavior | Safety impact |
| --- | --- | --- |
| Runtime preflight | Requires `RUN_MODE=READ_ONLY`, `RUN_MODE_EFFECTIVE=READ_ONLY`, execution disabled, event replay OFF, IBKR API write disabled, order submission disabled, clean-start disabled. | Fails closed before artifact assembly. |
| Dry-run mode | `--dry-run` writes generated placeholder artifacts and a manifest with `dry_run=true`, `broker_connected_runtime_artifact_captured=false`, `paper_ready=NO`, and status `DRY_RUN_VALIDATED_NOT_BROKER_EVIDENCE`. | Lets the operator validate the script path without broker connection or broker evidence overclaim. |
| Artifact completeness | Normal capture mode requires every PR1032 artifact JSON file by id. | Prevents partial operator-provided bundles from being treated as complete. |
| Contract validation | Reads PR1032 manifest template and checks required fields. | Keeps PR1033 aligned with PR1032. |
| Policy validation | Enforces zero order mutations, no order attempts, `paper_ready=NO`, and `paper_readiness_gate=FAIL`. | Prevents PAPER-readiness overclaiming. |
| Redaction | Redacts secret-like keys such as account id, token, credential, password, secret, and API key unless already marked redacted. | Reduces risk of publishing sensitive data. |
| Hashing | Computes SHA-256 for every normalized artifact copy. | Makes artifact review reproducible. |
| Manifest output | Emits `capture_manifest.json` with artifact paths, hashes, redaction status, and acceptance gate results. | Gives reviewers a single bundle index. |

## Required Operator Inputs For Real Capture

The script expects a source directory containing one JSON file per PR1032 artifact id when not using `--dry-run`:

```text
operator_runbook_acknowledgement.json
runtime_config_snapshot.json
broker_connection_snapshot.json
scanner_cycle_artifact.json
catalyst_news_artifact.json
watchlist_focus_artifact.json
pattern_input_artifact.json
setup_decision_artifact.json
risk_gate_artifact.json
execution_gate_artifact.json
broker_order_audit.json
analytics_storage_artifact.json
final_verdict.json
```

The script rejects the bundle if any file is missing, malformed, unsafe, or incomplete. Without `--dry-run`, `--source-dir` is required.

## Dry-Run Invocation

The operator runbook now contains the exact local command block for dry-run validation. The command uses `--dry-run` and omits `--source-dir`; the script generates placeholder artifacts and writes `capture_manifest.json` to the requested output directory.

Dry-run output is not broker-connected evidence. It does not prove live scanner data, catalyst/news data, broker order audit evidence, storage readback, numeric R:R, partial exits, trailing stops, breakeven movement, or PAPER readiness.

## Real Capture Invocation

```powershell
$env:RUN_MODE = "READ_ONLY"
$env:RUN_MODE_EFFECTIVE = "READ_ONLY"
$env:EXECUTION_ENABLED = "false"
$env:EXECUTION_ENABLED_EFFECTIVE = "false"
$env:EVENT_REPLAY_MODE = "OFF"
$env:EVENT_REPLAY_MODE_EFFECTIVE = "OFF"
$env:IBKR_API_WRITE_ALLOWED = "false"
$env:IBKR_ORDER_SUBMISSION_ENABLED = "false"
$env:FORCE_CLEAN_START = "false"

python scripts/certification/pr1033_readonly_broker_artifact_capture.py `
  --source-dir artifacts/certification/pr1033/raw_readonly_capture `
  --output-dir artifacts/certification/pr1033/validated_readonly_capture `
  --operator OPERATOR_INITIALS
```

## Hard Failure Conditions

The script aborts if any of these are true:

1. Runtime environment is not READ_ONLY.
2. Execution or IBKR order submission authority is enabled.
3. Event replay is active.
4. Clean-start is enabled.
5. Normal capture mode omits `--source-dir`.
6. Any required artifact file is missing in normal capture mode.
7. Required PR1032 fields are missing from any artifact.
8. Broker submitted/cancelled/modified order counts are nonzero.
9. Execution gate order attempts are nonzero.
10. Final verdict attempts `paper_ready=YES` or `paper_readiness_gate=PASS`.
11. Output directory is non-empty without `--force`.

## Remaining Blockers

| Blocker | Status after PR1033 |
| --- | --- |
| Real broker-connected READ_ONLY session evidence | Not captured by this PR |
| Zero-order broker audit from real session | Not captured by this PR |
| Durable storage write/readback from real session | Not captured by this PR |
| Numeric target/R:R certification | Still partial from prior PRs |
| Partial/trailing/breakeven lifecycle certification | Not certified |
| PAPER readiness | `NO` |

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py
python -m pytest tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py tests/test_ross_pr1031_readonly_full_session_paper_readiness_gate.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus or artifact"
```

Local execution may be unavailable in this Codex desktop session if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1033 adds offline READ_ONLY broker artifact capture tooling and dry-run validation. It does not connect to a broker, does not mutate broker state, does not enable PAPER/LIVE, and does not certify that the real broker-connected capture has already happened. Ross Momentum remains `PAPER_READY: NO`.
