## Implementation Tasks (if gaps exist)

A) Define artefact schemas
- ScanDecision
- StrategyDecision
- RiskDecision
- AllocationDecision
- ExecutionDecision
- NoTradeDecision

B) Ensure emit points exist in pipeline
- scanner output → ScanDecision
- strategy policy → StrategyDecision
- risk engine → RiskDecision
- allocator → AllocationDecision
- execution engine → ExecutionDecision

C) Persistence
- DB table(s) and/or append-only jsonl
- Must be queryable

D) Mode parity
- Artefacts generated in SIM/PAPER/LIVE/READ_ONLY