# PR1040 Real READ_ONLY Runtime Observation Adapter

## Scope

PR1040 adds a certification-only adapter for real Ross READ_ONLY runtime observation evidence after the PR1039 controlled smoke path.

This is not PAPER readiness. It does not enable PAPER or LIVE, does not submit, cancel, modify, preview-submit, stage, flatten, reconcile, or clean-start broker orders, and does not relax Ross thresholds or gates.

## Executive Verdict

PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
REAL_READ_ONLY_RUNTIME_OBSERVATION_ADAPTER_ADDED: YES
REAL_OPERATOR_CAPTURE_COMPLETED_BY_THIS_PR: NO
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
TRADING_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
PAPER_LIVE_ENABLED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO
MANUAL_FOCUS_READINESS_PROOF_ALLOWED: NO
SYNTHETIC_TRADE_INTENT_ALLOWED: NO
SYNTHETIC_ANALYTICS_STORAGE_PROOF_ALLOWED: NO

Final classification is determined only by the generated real observation JSON:

- READ_ONLY_OBSERVATION_VALID
- READ_ONLY_OBSERVATION_INVALID
- INSUFFICIENT_EVIDENCE

Default final posture remains:

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL

## Adapter

Script:

scripts/certification/pr1040_real_readonly_runtime_observation_adapter.py

The adapter sets READ_ONLY-only runtime overrides, runs the real scanner path through `run_scanner_cycle(mode="READ_ONLY")`, builds real pattern inputs through `build_runtime_pattern_inputs`, routes setup/decision authority through `RossMomentumStrategy.evaluate`, evaluates risk through `evaluate_trade_intents` in READ_ONLY mode only if canonical strategy output emits intents, keeps execution disabled, audits broker open orders before and after, and writes a PR1039-compatible `--observation-input` JSON.

The adapter no longer treats the PR1040 observation JSON write/readback as analytics/storage proof. Storage evidence is valid only when the runtime evidence source is `REAL_ANALYTICS_STORAGE_WRITE_READBACK`. No existing real analytics/storage write-readback source was identified in this patch, so operator runs without that source classify as `INSUFFICIENT_EVIDENCE` with this blocker:

`Real analytics/storage write-readback evidence is unavailable.`

The adapter fails closed if it observes:

- non-READ_ONLY runtime mode
- execution enabled
- IBKR API write authority enabled
- order submission enabled
- clean start enabled
- validation or threshold override enabled
- manual focus or prep-seeded focus evidence
- synthetic or forced trade intent markers
- accepted setup evidence from a non-canonical decision authority
- submitted/acknowledged/working/filled/cancelled/modified execution events
- broker open-order mutation before vs after the READ_ONLY observation

## Decision Authority

Accepted setup evidence must carry:

`decision_authority=RossMomentumStrategy.evaluate`

The adapter no longer calls `PatternEvaluator` and `build_trade_intents` directly as the certification authority. Pattern input evidence is still captured from the real runtime pattern-input builder, but setup/decision evidence comes from the canonical Ross strategy evaluation path. Under READ_ONLY runtime configuration, the canonical strategy may block intent emission; that is recorded honestly as no-trade or insufficient evidence rather than manufacturing an accepted setup.

## Output

Default PR1039-compatible observation input:

artifacts/certification/pr1040/real_runtime_observation/real_runtime_observation.json

Default PR1039 raw output:

artifacts/certification/pr1040/raw_real_runtime_observation/

Default PR1039 validated output:

artifacts/certification/pr1040/validated_real_runtime_observation/

## Operator Command

Run from the repository root with TWS or Gateway already connected in READ_ONLY-safe paper/data mode.

```powershell
$env:RUN_MODE="READ_ONLY"
$env:RUN_MODE_EFFECTIVE="READ_ONLY"
$env:EXECUTION_ENABLED="false"
$env:EXECUTION_ENABLED_EFFECTIVE="false"
$env:EVENT_REPLAY_MODE="OFF"
$env:EVENT_REPLAY_MODE_EFFECTIVE="OFF"
$env:IBKR_READONLY_ENABLED="true"
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
$env:SCANNER_DATA_SOURCE="IBKR"
$env:SCANNER_MODE="READ_ONLY"

.\.venv\Scripts\python.exe scripts\certification\pr1040_real_readonly_runtime_observation_adapter.py `
  --operator NELZON `
  --observation-output artifacts\certification\pr1040\real_runtime_observation\real_runtime_observation.json `
  --force
```

Expected default result until real storage proof exists:

```text
classification=INSUFFICIENT_EVIDENCE
paper_ready=NO
paper_readiness_gate=FAIL
```

## PR1039 Validation Command

```powershell
.\.venv\Scripts\python.exe scripts\certification\pr1039_readonly_full_ross_strategy_observation_producer.py `
  --observation-input artifacts\certification\pr1040\real_runtime_observation\real_runtime_observation.json `
  --raw-output-dir artifacts\certification\pr1040\raw_real_runtime_observation `
  --validated-output-dir artifacts\certification\pr1040\validated_real_runtime_observation `
  --operator NELZON `
  --force
```

The adapter can also run the PR1039 validation immediately:

```powershell
.\.venv\Scripts\python.exe scripts\certification\pr1040_real_readonly_runtime_observation_adapter.py `
  --operator NELZON `
  --validate-with-pr1039 `
  --force
```

## Evidence Requirements

A valid accepted setup requires all of the following:

- focused symbol present in Focus M
- catalyst status confirmed for focused symbols
- real runtime pattern input evidence captured and not blocked/unavailable
- non-synthetic setup/intent evidence
- `decision_authority=RossMomentumStrategy.evaluate`
- target model present from canonical strategy output
- risk_gate_called=true through READ_ONLY risk evaluation
- READ_ONLY risk decision source
- execution disabled
- broker order mutation count zero
- real analytics/storage write-readback evidence source

A valid no-trade observation is allowed only when it still contains full real pipeline evidence:

- scanner evidence
- catalyst/news evidence
- watchlist/focus evidence
- real pattern-input attempt and explicit missing/stale/block classification if blocked
- canonical setup/decision no-trade reason
- risk not approved
- execution disabled
- broker zero-order audit
- real analytics/storage write/readback evidence
- final PAPER_READY=NO and PAPER_READINESS_GATE=FAIL

If Focus M is empty, broker evidence is missing, pattern-input evidence is absent, canonical strategy decision evidence is absent, or storage/readback evidence is incomplete, the adapter classifies the result as INSUFFICIENT_EVIDENCE.

If the run observes unsafe execution, broker mutation, manual focus readiness proof, synthetic intent, non-canonical accepted setup evidence, or an accepted setup without required catalyst/risk/target evidence, the adapter classifies or fails the result as READ_ONLY_OBSERVATION_INVALID.

## Tests

Focused tests:

```powershell
.\.venv\Scripts\pytest.exe tests/test_ross_pr1040_real_readonly_runtime_observation_adapter.py -q
```

Relevant producer and collector regressions:

```powershell
.\.venv\Scripts\pytest.exe tests/test_ross_pr1039_readonly_full_strategy_observation_producer.py -q
.\.venv\Scripts\pytest.exe tests/test_ross_pr1038_readonly_full_strategy_observation_collector.py -q
```

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
```

## Certification Status

PR1040 provides the smallest safe real READ_ONLY adapter and PR1039-compatible observation-input format. It does not itself complete the human real-operator capture. The generated observation JSON must be reviewed and validated through PR1039 before any PAPER readiness discussion.

PAPER_READY remains NO.
PAPER_READINESS_GATE remains FAIL.
