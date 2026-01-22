# SYSTEM_STATE — Authoritative Project Status
Last updated: 2026-01-22

## Purpose
This file is the **single source of operational truth**.
It defines what is frozen, what is active, and what execution is allowed.

---
## Epoch Status

### Epoch 4 — COMPLETE (Frozen)
Scanner contract finalized:
Top N gainers → hard gates → Watchlist K → Focus M  
Empty watchlists are valid and must be explained.

### Epoch 5 — COMPLETE (Frozen)
Trading OS end‑to‑end pipeline complete:
Scanner → Strategy → Risk → Execution → Storage  
Determinism, explainability, and safety enforced.

### Epoch 9 — COMPLETE (Frozen)
**Strategy Portfolio Governance layer introduced:**
- Canonical Strategy Interface (intent normalization)
- Strategy Registry (enable/disable, priority)
- Deterministic arbitration (one strategy per symbol)
- Capital allocation governance
This epoch is infrastructure‑only and does **not** change strategy behaviour.

### Epoch 10 — IN PROGRESS (Isolated)
**Statistical Intraday Momentum strategy**
- Interface‑native strategy
- No Ross involvement
- No orchestrator rewiring yet
- Safe to develop and test in isolation

### Track A — Ross Momentum Live Track (ACTIVE)
Operational live rollout of Ross Momentum:
- Strategy‑driven stock selection enforced
- LIVE_MICRO (1 share) supported with hard risk caps
- Time‑of‑day aware behaviour
- Verified via mandatory verification commands

### Step 3 — Ross Interface Adapter (IN PROGRESS)
- Pure mapping layer: Ross → Strategy Interface
- **No logic change, no behaviour change**
- Adapter only; minimal routing update
- Ross remains live‑ready throughout

### Stabilisation Phase — COMPLETE (Frozen)
- Scanner market‑data alignment
- Watchlist lifecycle governance + observability
- DB auto‑recovery and ops summaries
- Mandatory verification commands enforced

### Parallel Learning Epoch — ACTIVE (Isolated)
- Read‑only analysis of events and trades
- Scheduled reports and reviews
- Policy proposals only — never auto‑applied

### Track B — Adaptive Regime / Microstructure Layer (Planned)
Sandboxed, deterministic, non‑mutating observational layer.

### Epoch 6 — FUTURE (Isolated)
Long‑horizon / Buffett‑style strategies.

---
## Frozen Truths (Non‑Negotiable)
- Scanner never trades
- Strategy emits **TradeIntent only**
- Interface normalizes intent; no strategy executes orders
- Risk is final authority
- Execution obeys mode, caps, and acknowledgements
- Storage is mandatory for all outcomes
- Learning never mutates live logic automatically

---
## Next Actions
- Complete Step 3 (Ross → Interface adapter) with full verification
- Continue Epoch 10 strategy development in isolation
- Proceed with controlled Track A LIVE_MICRO rollout
