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
BROKER_BEFORE_AFTER_AUDIT_COMPLETE_REQUIRED: YES
PRICED_INTENT_REQUIRED_FOR_ACCEPTED_SETUP: YES
READONLY_CONFIG_OVERRIDE_TYPES_GUARDED: YES
MARKET_DATA_DIAGNOSTIC_ADDED: YES
REAL_ANALYTICS_STORAGE_WRITE_READBACK_ADDED: NO
REAL_ANALYTICS_STORAGE_WRITE_READBACK_ADDED_BY_PR1044: NO
PR1044_STORAGE_PROOF_ADDED: NO
MANUAL_FOCUS_READINESS_PROOF_ALLOWED: NO
SYNTHETIC_TRADE_INTENT_ALLOWED: NO
SYNTHETIC_ANALYTICS_STORAGE_PROOF_ALLOWED: NO

## Exact PR1044 Scope Markers

PR1044_SCOPE: BOUNDED_OBSERVATION_AND_MARKET_DATA_DIAGNOSTIC_ONLY
BOUNDED_OBSERVATION_SCOPE_ONLY: YES
MARKET_DATA_DIAGNOSTIC_ONLY: YES
PR1044_COMPLETES_PR1043: NO
PR1044_COMPLETES_REAL_OPERATOR_CAPTURE: NO

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

The adapter sets READ_ONLY-only runtime overrides, runs the real scanner path through `run_scanner_cycle(mode="READ_ONLY")`, builds real pattern inputs through `build_runtime_pattern_inputs`, routes setup/decision authority through `RossMomentumStrategy.evaluate`, evaluates risk through `evaluate_trade_intents` in READ_ONLY mode only if canonical strategy output emits intents, keeps execution disabled, audits broker open orders before and after, records scanner market-data diagnostics, and writes a PR1039-compatible `--observation-input` JSON.

The adapter sends only PR1040 READ_ONLY launch guard keys into `set_config_overrides`. Inherited environment variables remain at normal ENV precedence so blank operator fields such as scanner symbol lists are not accidentally promoted to boolean `False` overrides. The scanner launch config value is `SCANNER_MODE=LIVE_READONLY`, while the adapter still records the observation run as `run_scanner_cycle(mode="READ_ONLY")`.

Broker connection evidence is complete only when both the before and after broker snapshots are connected and auditable. A one-sided broker snapshot is not enough and classifies as `INSUFFICIENT_EVIDENCE` with this blocker:

`Broker before/after audit evidence is incomplete.`

The adapter emits `market_data_diagnostic_artifact` from scanner diagnostics when they are present. If real scanner diagnostics report unavailable market data, the observation classifies as `INSUFFICIENT_EVIDENCE` with this blocker:

`Real market data diagnostic indicates scanner market data is unavailable.`

The adapter does not treat the PR1040 observation JSON write/readback as analytics/storage proof. PR1044 does not add or synthesize analytics/storage proof. Storage evidence is valid only when a real runtime evidence source records `REAL_ANALYTICS_STORAGE_WRITE_READBACK`; otherwise the observation classifies as `INSUFFICIENT_EVIDENCE` with this blocker:

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
- accepted setup risk evidence without a numeric entry price or equivalent canonical priced sizing input
- scanner market-data diagnostics that report unavailable market data
- incomplete broker before/after audit evidence
- submitted/acknowledged/working/filled/cancelled/modified execution events
- broker open-order mutation before vs after the READ_ONLY observation

## Decision Authority

Accepted setup evidence must carry:

`decision_authority=RossMomentumStrategy.evaluate`

The adapter does not call `PatternEvaluator` and `build_trade_intents` directly as the certification authority. Pattern input evidence is still captured from the real runtime pattern-input builder, but setup/decision evidence comes from the canonical Ross strategy evaluation path. Under READ_ONLY runtime configuration, the canonical strategy may block intent emission; that is recorded honestly as no-trade or insufficient evidence rather than manufacturing an accepted setup.

Accepted setup risk evidence also requires a usable numeric entry price or equivalent canonical priced sizing input. The adapter passes the parsed canonical strategy entry price into `TradeIntentRecord.entry_price`, the top-level field consumed by `evaluate_trade_intents` for sizing. For PR1040 certification only, the adapter supplies a non-canonical `READ_ONLY_CONFIG` account snapshot with positive configured capital so the priced READ_ONLY risk path can be exercised without broker order authority. READ_ONLY risk approval without priced intent evidence is not valid PR1040 proof.

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
$env:SCANNER_MODE="LIVE_READONLY"

.\.venv\Scripts\python.exe scripts\certification\pr1040_real_readonly_runtime_observation_adapter.py `
  --operator NELZON `
  --observation-output artifacts\certification\pr1040\real_runtime_observation\real_runtime_observation.json `
  --force
```

Expected default result until real storage proof and complete market-data evidence exist:

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
- real scanner market-data diagnostics must not report unavailable data
- real runtime pattern input evidence captured and not blocked/unavailable
- non-synthetic setup/intent evidence
- `decision_authority=RossMomentumStrategy.evaluate`
- numeric entry price or equivalent canonical priced sizing input
- target model present from canonical strategy output
- risk_gate_called=true through READ_ONLY risk evaluation
- READ_ONLY risk decision source
- execution disabled
- before and after broker snapshots connected
- broker order mutation count zero
- real analytics/storage write-readback evidence source

A valid no-trade observation is allowed only when it still contains full real pipeline evidence:

- scanner evidence
- scanner market-data diagnostic artifact
- catalyst/news evidence
- watchlist/focus evidence
- real pattern-input attempt and explicit missing/stale/block classification if blocked
- canonical setup/decision no-trade reason
- risk not approved
- execution disabled
- before and after broker snapshots connected
- broker zero-order audit
- real analytics/storage write/readback evidence
- final PAPER_READY=NO and PAPER_READINESS_GATE=FAIL

If Focus M is empty, scanner market-data diagnostics report unavailable data, before/after broker evidence is incomplete, pattern-input evidence is absent, canonical strategy decision evidence is absent, or storage/readback evidence is incomplete, the adapter classifies the result as INSUFFICIENT_EVIDENCE.

If the run observes unsafe execution, broker mutation, manual focus readiness proof, synthetic intent, non-canonical accepted setup evidence, accepted setup risk evidence without a numeric entry price, or an accepted setup without required catalyst/risk/target evidence, the adapter classifies or fails the result as READ_ONLY_OBSERVATION_INVALID.

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

PR1040 provides the smallest safe real READ_ONLY adapter and PR1039-compatible observation-input format. PR1044 keeps this patch bounded to priced READ_ONLY risk evidence and scanner market-data diagnostics; it does not complete human real-operator capture and does not add analytics/storage readiness proof. The generated observation JSON must still be reviewed and validated through PR1039 before any PAPER readiness discussion.

PAPER_READY remains NO.
PAPER_READINESS_GATE remains FAIL.
