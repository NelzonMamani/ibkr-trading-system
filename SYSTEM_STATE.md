# SYSTEM STATE

**This file is the single source of truth.**  
If code or other documents disagree with this file, this file wins.

---

## Epoch progress

- Epoch 1 — Market Perception: COMPLETE
- Epoch 2 — Decision Intelligence: COMPLETE
- Epoch 3 — Risk & Execution: COMPLETE
- Epoch 4 — Trade Lifecycle & Persistence: COMPLETE (LOCKED)

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

1) Preserve Epoch 4 storage/timeline/reporting determinism and safety gates.
2) Proceed with the next epoch only after governance updates.

---

## Notes

- The constitution is immutable. Do not edit `SYSTEM_CONSTITUTION.md`.
- Epoch governance defines the scope of permitted work.
