
# E22 Architecture and Components

## Placement in runtime pipeline
Canonical pipeline (conceptual):

1) Market session detection
2) Universe build (scanner / watchlist K / focus M)
3) Strategy evaluation (per strategy) -> produces `TradeIntent[]`
4) **E22: Strategy Scalability & Arbitration Layer**
5) Risk engine (position sizing, exposures, session limits)
6) Execution engine (broker submitter / provider)
7) Persistence (events + evidence)

E22 is a **coordination layer** with two core responsibilities:
- **Scalability governance**: budgets + shared caches + coalescing
- **Arbitration governance**: resolve conflicts, prioritise, produce final actionable intents

## Core components (logical)
### A) StrategyScheduler
- Determines which strategies run in a cycle and in what order
- Enforces per-cycle budgets (hard caps)
- Emits scheduling audit events

### B) SharedDataCoordinator
- Provides strategy-safe APIs for data pulls that can be cached/coalesced:
  - snapshots
  - bars
  - fundamentals / float cache
  - news gating (if present)
- Enforces “one request per symbol per cycle” invariants when possible
- Emits data-provenance tags (ties to M10)

### C) IntentArbitrator
- Accepts intents from multiple strategies
- Applies conflict policy:
  - symbol exclusivity (optional per instrument class)
  - portfolio exposure bounds
  - per-strategy priority weights
  - tie-breakers (confidence, liquidity, recency, deterministic hash)
- Produces:
  - allowed intents (final)
  - suppressed intents
  - arbitration report (JSON + MD)

### D) ArbitrationEvidenceWriter
- Writes evidence bundle for each run/cycle:
  - `arbitration_report.json`
  - `arbitration_report.md`
  - `EVIDENCE_INDEX.json`
- Updates/feeds system integrity reporter as appropriate

## Determinism strategy
Determinism is achieved by:
- stable ordering of strategy evaluation
- stable ordering of intents (sorting keys)
- stable tie-breakers (explicit policy; never “random”)
- coalesced data pulls that return stable snapshots for the cycle

## Concurrency model (governed)
E22 does not require “fully async everything”. It requires:
- explicit concurrency ceilings
- budgets expressed as integers per cycle
- fail-closed behaviour on budget breaches

Recommended:
- concurrency token bucket per data type
- per-strategy token budgets
