# PR1039 READ_ONLY Full Ross Strategy Observation Producer

## Scope

PR1039 adds certification-only tooling to produce a controlled READ_ONLY Ross observation artifact bundle and immediately validate that bundle through the PR1038 validator.

PR1038 validates the raw artifact set, but PR1038 does not produce that raw set. PR1039 fills the next gap by adding a strict producer/adapter that writes the PR1038-required raw artifacts and calls the PR1038 validator.

This PR is still not PAPER readiness. It does not connect to IBKR in CI. It does not submit, cancel, modify, preview-submit, stage, flatten, reconcile, or clean-start broker state. It does not alter Ross thresholds. It does not weaken Ross gates. It does not enable PAPER or LIVE.

## Executive Verdict

PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
READ_ONLY_FULL_STRATEGY_OBSERVATION_PRODUCER_ADDED: YES
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO
CI_CONNECTS_TO_IBKR: NO
REAL_OPERATOR_CAPTURE_COMPLETED_BY_THIS_PR: NO

Ross Momentum remains `PAPER_READY: NO`.

## What PR1039 Produces

PR1039 writes the raw artifacts required by PR1038:

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

Default raw output directory:
artifacts/certification/pr1039/raw_readonly_full_ross_observation/

Default validated output directory:
artifacts/certification/pr1039/validated_readonly_full_ross_observation/

## Safety Gates

PR1039 fails closed before writing or validating when any safety setting is unsafe.

| Gate | Required result |
| --- | --- |
| Runtime mode | RUN_MODE=READ_ONLY and RUN_MODE_EFFECTIVE=READ_ONLY |
| Execution | EXECUTION_ENABLED=false and EXECUTION_ENABLED_EFFECTIVE=false |
| IBKR write authority | IBKR_API_WRITE_ALLOWED=false |
| Order submission | IBKR_ORDER_SUBMISSION_ENABLED=false |
| Clean-start | FORCE_CLEAN_START=false |
| Ross validation override | ROSS_VALIDATION_OVERRIDE_ENABLED=false; legacy ROSS_VALIDATION_OVERRIDE=false if present |
| Threshold override | absent or false |
| Catalyst bypass | absent or false |
| Float/RVOL relaxation | absent or false |
| Manual focus | absent/empty/false |
| Synthetic trade intent | absent/empty/false |
| Broker order mutation | submitted/cancelled/modified/order-attempt counts all zero |
| Accepted setup catalyst | at least one focused symbol and confirmed catalyst required for focused symbols |
| Accepted setup pattern inputs | fresh/non-blocked required |
| Accepted setup models | entry, stop, and target models required |
| Accepted setup risk | risk_gate_called=true and real READ_ONLY risk source required |
| No-trade risk | cannot have risk_approved=true |
| Final verdict | paper_ready=NO and paper_readiness_gate=FAIL |

## Valid Observation Outcomes

A valid no-trade observation is acceptable when the artifact bundle proves that Ross observed the scanner/focus/pattern/decision path and blocked/no-traded for explicit Ross-correct reasons.

A valid accepted setup observation is acceptable only when catalyst is confirmed, pattern inputs are fresh/non-blocked, entry/stop/target are present, risk evaluation is real, execution remains disabled, and broker order audit remains zero.

PR1039 must not force a trade.

## Operator Command

Use this after PR1039 is merged or during local certification-harness verification.

cd "C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system"
$env:RUN_MODE="READ_ONLY"
$env:RUN_MODE_EFFECTIVE="READ_ONLY"
$env:EXECUTION_ENABLED="false"
$env:EXECUTION_ENABLED_EFFECTIVE="false"
$env:EVENT_REPLAY_MODE="OFF"
$env:EVENT_REPLAY_MODE_EFFECTIVE="OFF"
$env:IBKR_API_WRITE_ALLOWED="false"
$env:IBKR_ORDER_SUBMISSION_ENABLED="false"
$env:FORCE_CLEAN_START="false"
$env:FORCE_EXECUTION_ON_TRADE_READY="false"
$env:FORCE_RISK_APPROVAL_FOR_TRADE_READY="false"
$env:VALIDATION_SESSION_OVERRIDE="false"
$env:ROSS_VALIDATION_OVERRIDE="false"
$env:ROSS_VALIDATION_OVERRIDE_ENABLED="false"
$env:ROSS_THRESHOLD_OVERRIDE="false"
$env:ROSS_CATALYST_BYPASS="false"
$env:ROSS_FLOAT_RELAXATION="false"
$env:ROSS_RVOL_RELAXATION="false"
$env:MANUAL_FOCUS_ENABLED="false"
$env:SYNTHETIC_TRADE_INTENT_ENABLED="false"
$env:MANUAL_FOCUS_SYMBOLS=""
$env:ROSS_MANUAL_FOCUS_SYMBOLS=""
$env:SYNTHETIC_TRADE_INTENTS=""
$env:ROSS_SYNTHETIC_TRADE_INTENTS=""

.\.venv\Scripts\python.exe scripts\certification\pr1039_readonly_full_ross_strategy_observation_producer.py `
  --raw-output-dir artifacts\certification\pr1039\raw_readonly_full_ross_observation `
  --validated-output-dir artifacts\certification\pr1039\validated_readonly_full_ross_observation `
  --operator NELZON `
  --scenario valid_no_trade `
  --force

## Verification

python -m compileall -q src tests scripts
python -m pytest tests/test_ross_pr1039_readonly_full_strategy_observation_producer.py
python -m pytest tests/test_ross_pr1038_readonly_full_strategy_observation_collector.py
python -m pytest tests/test_ross_pr1037_pr1034_ib_insync_connect_timeout.py
python -m pytest tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py
python -m pytest tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py
python -m pytest tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py

## Remaining Blockers

| Blocker | Status after PR1039 |
| --- | --- |
| Real production Ross runtime adapter | Still required |
| Real operator READ_ONLY full strategy observation | Not completed by this PR |
| Human review of real artifacts | Still required |
| PAPER readiness | NO |
| PAPER readiness gate | FAIL |

## Final Certification Answer

PR1039 adds a controlled READ_ONLY observation producer/adapter that writes PR1038-compatible raw artifacts and validates them through PR1038. It does not enable PAPER/LIVE, does not mutate broker state, does not change Ross thresholds, and does not weaken Ross gates. Real operator capture and human artifact review remain required. Ross Momentum remains `PAPER_READY: NO`.

