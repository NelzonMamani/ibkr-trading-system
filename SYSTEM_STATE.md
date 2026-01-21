# SYSTEM_STATE — Authoritative Project Status
Last updated: 2026-02-01

## Purpose
This file is the single source of operational truth.
It defines what is frozen, what is active, and what execution is allowed.

---
## Epoch Status
### Epoch 4 — COMPLETE (Frozen)
Scanner contract finalized:
Top N gainers → hard gates → Watchlist K → Focus M
Empty watchlists are valid and must be explained.

### Epoch 5 — COMPLETE (Frozen)
Trading OS end-to-end pipeline complete:
Scanner → Patterns → Strategy → Risk → Execution → Storage
Includes determinism, explainability, and safety enforcement.

### Track A — Ross Momentum Live Track (ACTIVE)
Operational live rollout of Ross Momentum:
- Strategy-driven stock selection enforced
- LIVE_MICRO (1 share) supported with hard risk caps
- Time-of-day aware behaviour
- Manual verification and incremental hardening ongoing

### Stabilisation Phase — COMPLETE (Frozen)
- LIVE_MICRO scanner market data alignment (read-only no longer blocks snapshots)
- Watchlist lifecycle governance + print observability
- DB auto-recovery, startup banner, and ops summary hooks
- Mandatory verification commands enforced as the gate

### Parallel Learning Epoch — ACTIVE (Isolated)
- Read-only analysis of events and trades
- Daily/weekly/monthly/yearly reports + trade reviews
- Policy proposals only — never auto-applied
- Scheduler catches missed reports on startup/shutdown

### Track B — Adaptive Regime / Microstructure Layer (PLANNED)
Sandboxed, deterministic, non-mutating observational layer.

### Epoch 6 — FUTURE (Isolated)
Long-horizon / Buffett-style strategies.

---
## Frozen Truths (Non-Negotiable)
- Scanner never trades
- Strategy emits TradeIntent only
- Risk is final authority
- Execution obeys mode and constraints
- Storage is mandatory for all outcomes
- Learning never mutates live logic automatically

---
## Next Action
Run mandatory verification commands and proceed with controlled Track A live rollout,
keeping Parallel Learning outputs in proposal-only mode.
