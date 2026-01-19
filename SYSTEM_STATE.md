# SYSTEM_STATE — Authoritative Project Status
Last updated: 2026-01-19

## Purpose
This file is the **single source of operational truth**.
It defines what is frozen, what is active, and what is permitted to execute.

---
## Epoch Status

### Epoch 4 — COMPLETE (Frozen)
Scanner contract finalized:
Top N gainers → hard gates → Watchlist K → Focus M  
Empty watchlists are valid and must be explained.

### Epoch 5 — COMPLETE (Frozen)
Trading OS end-to-end pipeline complete:
Scanner → Patterns → Strategy → Risk → Execution → Storage

Includes:
- Deterministic orchestration
- Explainability at every stage
- Safety enforcement across all run modes
- Full event capture and replay

### Track A — Ross Momentum Live Track (ACTIVE)
Operationalization of Ross Cameron–style momentum trading:
- Multiple momentum families (gap-and-go, continuation, pullback)
- Time-of-day aware behaviour
- Teaching-first → LIVE_MICRO progression
- Live wiring verified; semantic refinement ongoing

### Adaptive Regime / Microstructure Layer — PLANNED (Governed)
A cross-strategy intelligence layer designed to:
- Observe market regime and microstructure conditions
- Adjust strategy weights, confidence, and gating
- Never mutate or override strategy rules
- Remain deterministic across SIM and LIVE_READ_ONLY

This layer is **not yet implemented** and introduces **no execution risk**.

### Epoch 6 — FUTURE (Isolated)
Long-horizon / Buffett-style strategies.
Separate cadence, data, and risk profile.
No shared execution path with intraday strategies.

---
## Frozen Truths (Non-Negotiable)
- Scanner never trades
- Strategies emit TradeIntent only
- Risk is final authority
- Execution obeys run-mode constraints
- Storage is mandatory for all outcomes

---
## Next Action
Implement the **Adaptive Regime / Microstructure Layer** under explicit phase governance,
then resume semantic refinement of Track A strategies.

## Authority Note
Intraday strategy implementations under `src/strategies/*` are authoritative.
Legacy adapters remain for compatibility only and must not be extended.
