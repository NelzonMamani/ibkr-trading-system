# EPOCH 4 — TRADE LIFECYCLE & PERSISTENCE GOVERNANCE (AUTHORITATIVE)

## Purpose

Epoch 4 formalizes **trade lifecycle persistence** so the system becomes:
- auditable
- replayable
- explainable from stored facts (not recomputation)
- safe to debug and evolve without losing determinism

Epoch 4 introduces a canonical, durable representation of:
- decisions, intents, and gates
- execution attempts and outcomes (including blocked/duplicate/rejected)
- exit decisions and trade outcomes
- performance snapshots and derived reports
- event timelines for replay

This governance constrains what may be implemented in Epoch 4 and how.

---

## Scope

### In scope
- Canonical storage schema for a full orchestrator cycle and trade lifecycle
- SQLite persistence (already used) as the reference backend
- Deterministic serialization and schema migration discipline
- Replay/timeline reconstruction from persisted data
- Reporting derived from stored records (not from transient in-memory state)
- Storage CLI and export utilities (CSV/JSON) for audits

### Out of scope (explicit)
- New strategy logic (beyond wiring storage hooks)
- Any expansion of broker execution capabilities
- Live trading enablement
- New risk models or sizing (beyond storing what exists)

---

## Non-negotiable invariants (must hold)

1) **Storage is append-first**: records are created per cycle; updates must be explicit, minimal, and explained.
2) **Determinism**: replay MUST reconstruct the same decisions from stored inputs; no hidden recomputation from market data.
3) **Explainability**: every stored decision must carry reason tags/rationales.
4) **Governance hierarchy**: this file cannot override `SYSTEM_CONSTITUTION.md` or `SYSTEM_STATE.md`.
5) **Safety**: execution remains disabled by default; storage work must not relax gating.
6) **Separation**: strategy outputs are stored via canonical contracts; strategy internals remain isolated.

---

## Authoritative deliverables (Epoch 4 phases)

### Phase 35 — Trade Storage Canonical Schema
- Define canonical schema objects:
  - Run, Cycle, TradeRecord, Event, Trade, ExecutionAttempt, ExitDecision, TradeOutcome, PerformanceSnapshot
- SQLite tables and indices aligned to query patterns
- Serialization layer: stable JSON encoding for nested payloads
- Tests proving:
  - persistence round-trip
  - schema constraints and invariants
  - idempotent inserts where intended (e.g., run_id)

### Phase 36 — Replay & Timeline Authority
- Replay engine reads from storage snapshots and event tables
- Timeline reconstruction:
  - cycle boundaries
  - causal ordering
  - stable event schemas
- Live modes remain replay-locked (no change)

### Phase 37 — Performance Reports from Storage
- Performance metrics computed from stored TradeOutcomes and ExecutionAttempts
- Reports must be reproducible from DB contents alone
- Tests verify:
  - determinism
  - report schema compatibility

### Phase 38 — Storage CLI & Audit Exports
- CLI utilities to:
  - inspect last run/cycle
  - export run timeline
  - export trade outcomes and performance summaries
- Export formats:
  - JSON (lossless)
  - CSV (human tools)

---

## Acceptance criteria (Epoch 4 completion gate)

Epoch 4 is COMPLETE only when:

- All Phase 35–38 deliverables exist and meet their acceptance tests.
- Replay is deterministic from persisted data (no market-data recomputation).
- Storage schema is documented and stable.
- Audit exports enable offline inspection of a run without executing the system.

When complete, update:
- `SYSTEM_STATE.md` -> mark Epoch 4 COMPLETE
- `README.md` -> reflect Epoch 4 COMPLETE

Do NOT modify `SYSTEM_CONSTITUTION.md`.
