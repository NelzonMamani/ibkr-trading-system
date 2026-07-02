# PR1038 READ_ONLY Full Ross Strategy Observation Collector

## Scope

PR1038 adds certification-only tooling for the next Ross Momentum readiness gate after the successful PR1034/PR1037 broker-connected READ_ONLY shell capture.

PR1034/PR1037 proved broker-connected READ_ONLY shell capture and zero broker order mutations. That shell evidence is necessary, but it is not the same as a full Ross strategy runtime observation.

PR1038 adds an offline validator/assembler for a controlled READ_ONLY full Ross observation bundle. The operator must provide captured JSON artifacts from a real READ_ONLY observation run. The PR1038 validator checks Ross-specific safety conditions, delegates redaction/hashing to the PR1033 validator, and emits a PR1038 manifest overlay.

This PR does not connect to IBKR in CI. It does not submit, cancel, modify, preview-submit, stage, flatten, reconcile, or clean-start broker state. It does not enable PAPER or LIVE. It does not change Ross strategy thresholds. It does not weaken Ross gates.

## Executive Verdict

``text
PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATOR_ADDED: YES
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO
CI_CONNECTS_TO_IBKR: NO
REAL_OPERATOR_CAPTURE_COMPLETED_BY_THIS_PR: NO
``

Ross Momentum remains `PAPER_READY: NO`.

## What PR1038 Validates

The validator expects a source directory containing the PR1032/PR1033 artifact set:

``text
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
``

## Additional PR1038 Safety Gates

| Gate | Required result |
| --- | --- |
| Runtime mode | RUN_MODE=READ_ONLY and RUN_MODE_EFFECTIVE=READ_ONLY |
| Execution | EXECUTION_ENABLED=false and EXECUTION_ENABLED_EFFECTIVE=false |
| IBKR write authority | IBKR_API_WRITE_ALLOWED=false |
| Order submission | IBKR_ORDER_SUBMISSION_ENABLED=false |
| Clean-start | FORCE_CLEAN_START=false |
| Force execution | absent or false |
| Force risk approval | absent or false |
| Ross validation override | absent or false |
| Threshold override | absent or false |
| Catalyst bypass | absent or false |
| Float/RVOL relaxation | absent or false |
| Manual focus | absent/empty/false |
| Synthetic trade intent | absent/empty/false |
| Broker order mutation | submitted/cancelled/modified/order-attempt counts all zero |
| Open-order stability | before/after snapshots unchanged |
| Catalyst | accepted setup requires confirmed catalyst for focused symbols |
| Pattern inputs | accepted setup cannot use blocked, stale, or missing pattern inputs |
| Risk | rejected/no-trade setup cannot receive fake risk approval |
| Execution gate | execution remains disabled and order attempts remain zero |
| Storage | missing storage readback requires an explicit final blocker |
| Final verdict | paper_ready=NO and paper_readiness_gate=FAIL |

## Important No-Trade Rule

PR1038 must not force a trade. A valid no-trade observation is acceptable when it proves the real READ_ONLY path observed scanner, catalyst, focus, pattern input, setup/decision, risk, execution-disabled, broker audit, and storage/readback evidence and records explicit no-trade or block reasons.

That rule is intentional. Ross must not invent a setup when the market does not provide a valid Ross play.

## Operator Command

Use this after the real READ_ONLY observation artifacts have been written to the raw source directory.

``powershell
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
.\.venv\Scripts\python.exe scripts\certification\pr1038_readonly_full_ross_strategy_observation_collector.py `
  --source-dir artifacts\certification\pr1038\raw_readonly_full_ross_observation `
  --validated-output-dir artifacts\certification\pr1038\validated_readonly_full_ross_observation `
  --operator NELZON
``

## Verification

``powershell
python -m compileall -q src tests scripts
python -m pytest tests/test_ross_pr1038_readonly_full_strategy_observation_collector.py
python -m pytest tests/test_ross_pr1037_pr1034_ib_insync_connect_timeout.py
python -m pytest tests/test_ross_pr1036_pr1034_ib_insync_import_order_bootstrap.py
python -m pytest tests/test_ross_pr1035_pr1034_broker_collector_safety_fix.py
python -m pytest tests/test_ross_pr1034_readonly_broker_connected_artifact_collector.py
python -m pytest tests/test_ross_pr1033_readonly_broker_artifact_capture_script.py
python -m pytest tests/test_ross_pr1032_readonly_broker_runtime_artifact_capture_pack.py
``

## Remaining Blockers

| Blocker | Status after PR1038 |
| --- | --- |
| Real operator READ_ONLY full strategy observation | Not captured by this PR |
| Human review of full observation artifacts | Still required |
| PAPER readiness | NO |
| PAPER readiness gate | FAIL |

## Final Certification Answer

PR1038 adds an offline READ_ONLY full Ross strategy observation validator. It does not connect to IBKR, does not mutate broker state, does not enable PAPER/LIVE, does not change Ross thresholds, and does not weaken Ross gates. The next action is for the operator to capture a real READ_ONLY full strategy observation bundle and validate it with this script. Ross Momentum remains `PAPER_READY: NO`.

