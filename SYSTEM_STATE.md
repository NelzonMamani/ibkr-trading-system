# SYSTEM STATE

**This file is the single source of truth.**  
If code or other documents disagree with this file, this file wins.

---

## Epoch progress

- Epoch 1 — Market Perception: COMPLETE
- Epoch 2 — Decision Intelligence: COMPLETE
- Epoch 3 — Risk & Execution: COMPLETE
- Epoch 4 — Trade Lifecycle & Persistence: ACTIVE (not yet completed)

---

## What is enabled right now (authoritative)

- Market data: **allowed** in `LIVE_READ_ONLY` when configured and IBKR is available
- Execution: **HARD DISABLED by default**; order routing must remain blocked unless explicitly enabled by governance and configuration
- Replay: locked down in `LIVE` / `LIVE_READ_ONLY` / `LIVE_MICRO` by safety policy (replay is for SIM and offline modes)

---

## Epoch 4 intent (authoritative)

Epoch 4 makes the system **auditable** and **replayable** by defining a canonical storage model for:
- scanner outputs
- pattern/signal evaluations
- strategy intents
- risk decisions
- execution results
- exits/trade outcomes
- performance snapshots
- event timelines

The result is a deterministic, queryable record of each orchestrator cycle and each trade lifecycle.

---

## Epoch 4 phases (authoritative)

- Phase 35 — Trade Storage Canonical Schema
- Phase 36 — Replay & Timeline Authority
- Phase 37 — Performance Reports from Storage
- Phase 38 — Storage CLI & Audit Exports

---

## Immediate next actions (authoritative)

1) Implement Phase 35 end-to-end: storage schema + persistence adapters + tests.
2) Implement Phase 36: replay uses stored records/events to reconstruct the full timeline deterministically.
3) Implement Phase 37: reports read from storage (no ad-hoc calculations that bypass storage).
4) Implement Phase 38: CLI tools + export formats for audits and debugging.
5) Update this file to mark Epoch 4 COMPLETE only when all four phases have:
   - deterministic behavior
   - passing tests
   - documented acceptance criteria satisfied

---

## Notes

- The constitution is immutable. Do not edit `SYSTEM_CONSTITUTION.md`.
- Epoch governance defines the scope of permitted work.
