# MODULE_REQUIREMENTS_storage
Last updated: 2026-01-15

## 1. Purpose
Storage provides auditability and replayability. It is non-optional.
If something happens and it is not persisted, it effectively did not happen.

## 2. What Must Be Persisted (Minimum)
- ScannerArtifact each cycle
- PatternResults for Focus symbols
- TradeIntents emitted by strategies
- RiskDecisions for each intent
- ExecutionEvents and final order outcomes (when applicable)
- HealthSnapshots per cycle
- Errors/warnings (broker, data, system)

## 3. Linking Requirement (Critical)
Every stored record must link the chain:
ScannerArtifact → PatternResults → TradeIntent → RiskDecision → ExecutionEvents → Outcome

Use shared identifiers:
- cycle_id
- intent_id
- order_id (if applicable)
- symbol

## 4. Storage Schema (Minimum Fields)
- timestamps: created_at, cycle_time
- run mode, session_state
- symbol, setup_id
- metrics (scanner)
- intent parameters (entry/stop/targets)
- risk decisions (triggered rules + rationale)
- execution events (status progression)
- P&L and R-multiple where applicable
- data quality flags and health state

## 5. Storage Failure Behaviour
- Storage failure must be loud (print + error record)
- In READONLY/SIM: may continue with DEGRADED health if transient
- In LIVE_1SHARE: inability to persist trade-relevant events should trigger CRITICAL and halt new entries

## 6. Reporting
Storage should support:
- per-day summaries (trades, win rate, expectancy)
- drop-reason histograms
- pattern performance stats (future epochs can expand)

END.
