
# E22 Intent and Scope

## Intent
Provide a **first-class arbitration and scalability layer** that supports running up to **20 strategies** in the Trading OS while preserving:

- Safety: run-mode and permission gating remains authoritative
- Risk invariants: portfolio/risk constraints enforced consistently
- Determinism: stable ordering, stable outcomes given same inputs
- Auditability: every allow/deny decision has a traceable reason code
- Performance: bounded per-cycle latency and bounded external calls

## Scope (in)
E22 defines:

1) **Strategy scheduling governance**
   - deterministic cycle ordering
   - per-strategy budgets: snapshots, scanner calls, bar requests, compute time
2) **Shared data access patterns**
   - request coalescing / de-duplication
   - caching rules with TTL + provenance tags
3) **Arbitration & conflict resolution**
   - symbol-level exclusivity rules
   - intent merging or suppression rules
   - priority policy + tie-breakers
4) **Cross-strategy portfolio and risk coordination**
   - centralized “final decision” interface (already exists in risk/execution) with E22-specific pre-aggregation
5) **Audit artifacts**
   - deterministic arbitration reports per cycle
   - evidence indices + certification verdict integration

## Scope (out) / Non-goals
- Inventing new strategies or changing existing strategy alpha logic
- Redesigning IBKR adapters
- Rewriting the orchestrator architecture (E22 is additive, grafted as a layer)

## Key deliverable
A canonical “Arbitration Decision Artifact” per cycle:
- inputs: strategy intents + relevant context
- outputs: final permitted intents + suppressed intents + reasons + ranks
- evidence: stable JSON + human-readable Markdown summary
