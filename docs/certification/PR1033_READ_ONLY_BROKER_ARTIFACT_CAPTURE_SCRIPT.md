# PR1033 READ_ONLY Broker Artifact Capture Script

## Scope

PR1033 adds the READ_ONLY broker artifact capture script that operationalizes the PR1032 runbook and manifest contract. The script assembles and validates operator-provided JSON artifacts from a future broker-connected READ_ONLY run, redacts secret-like fields, computes SHA-256 hashes, writes normalized artifact copies, and emits a review manifest.

This PR does not connect to IBKR. It does not submit, cancel, modify, preview-submit, stage, flatten, or reconcile broker orders. It does not enable PAPER or LIVE. It does not certify that a broker-connected session has already happened.

## Executive Verdict

```text
PAPER_READY: NO
READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT: ADDED
SCRIPT_CONNECTS_TO_BROKER: NO
SCRIPT_SUBMITS_ORDERS: NO
SCRIPT_CANCELS_OR_MODIFIES_ORDERS: NO
SCRIPT_FLATTENS_POSITIONS: NO
BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO
PRODUCTION_TRADING_CODE_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
PAPER_LIVE_ENABLED: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Use the PR1033 script during a future operator-controlled READ_ONLY broker artifact capture run with real, redacted, hashable artifacts.
DO_NOT_GO_PAPER_REASON: PR1033 adds offline artifact capture tooling only; it does not contain real broker-connected runtime evidence, zero-order broker audit proof from a live session, durable storage readback proof from a live session, numeric R:R certification, or partial/trailing/breakeven lifecycle certification.
```

PAPER readiness remains blocked.

## Files Added

| File | Purpose |
| --- | --- |
| `scripts/certification/pr1033_readonly_broker_artifact_capture.py` | Offline READ_ONLY artifact validator/assembler. |
| `tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py` | Tests for safe env enforcement, complete artifact contract, redaction, hashing, and no-overclaim report language. |
| `docs/certification/PR1033_READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT.md` | Certification report for PR1033 scope and remaining blockers. |

## Script Behavior

| Capability | Behavior | Safety impact |
| --- | --- | --- |
| Runtime preflight | Requires `RUN_MODE=READ_ONLY`, `RUN_MODE_EFFECTIVE=READ_ONLY`, execution disabled, event replay OFF, IBKR API write disabled, order submission disabled, clean-start disabled. | Fails closed before artifact assembly. |
| Artifact completeness | Requires every PR1032 artifact JSON file by id. | Prevents partial bundle from being treated as complete. |
| Contract validation | Reads PR1032 manifest template and checks required fields. | Keeps PR1033 aligned with PR1032. |
| Policy validation | Enforces zero order mutations, no order attempts, `paper_ready=NO`, and `paper_readiness_gate=FAIL`. | Prevents PAPER-readiness overclaiming. |
| Redaction | Redacts secret-like keys such as account id, token, credential, password, secret, and API key unless already marked redacted. | Reduces risk of publishing sensitive data. |
| Hashing | Computes SHA-256 for every normalized artifact copy. | Makes artifact review reproducible. |
| Manifest output | Emits `capture_manifest.json` with artifact paths, hashes, redaction status, and acceptance gate results. | Gives reviewers a single bundle index. |

## Required Operator Inputs

The script expects a source directory containing one JSON file per PR1032 artifact id:

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

The script rejects the bundle if any file is missing, malformed, unsafe, or incomplete.

## Example Invocation

```powershell
$env:RUN_MODE = "READ_ONLY"
$env:RUN_MODE_EFFECTIVE = "READ_ONLY"
$env:EXECUTION_ENABLED = "false"
$env:EXECUTION_ENABLED_EFFECTIVE = "false"
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
5. Any required artifact file is missing.
6. Required PR1032 fields are missing from any artifact.
7. Broker submitted/cancelled/modified order counts are nonzero.
8. Execution gate order attempts are nonzero.
9. Final verdict attempts `paper_ready=YES` or `paper_readiness_gate=PASS`.
10. Output directory is non-empty without `--force`.

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

PR1033 adds offline READ_ONLY broker artifact capture tooling. It does not connect to a broker, does not mutate broker state, does not enable PAPER/LIVE, and does not certify that the real broker-connected capture has already happened. Ross Momentum remains `PAPER_READY: NO`.
