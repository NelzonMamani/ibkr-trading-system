# SYSTEM_STATE — Authoritative Project Status
Last updated: 2026-02-01

## Purpose
This file is the **single source of operational truth**.
It defines what is frozen, what is active, what is prepared, and what execution is allowed.

---

## Epoch Status

### Epoch 4 — COMPLETE (Frozen)
Scanner contract finalized:
Top N gainers → hard gates → Watchlist K → Focus M  
Empty watchlists are valid and must be explained.

### Epoch 5 — COMPLETE (Frozen)
Trading OS end-to-end pipeline complete:
Scanner → Strategy → Risk → Execution → Storage  
Determinism, explainability, and safety enforced.

### Epoch 9 — COMPLETE (Frozen)
**Strategy Portfolio Governance layer introduced:**
- Canonical Strategy Interface (intent normalization)
- Strategy Registry (enable/disable, priority)
- Deterministic arbitration (one strategy per symbol)
- Capital allocation governance  
This epoch is infrastructure-only and does **not** change strategy behaviour.

### Epoch 10 — IN PROGRESS (Isolated)
**Statistical Intraday Momentum strategy**
- Interface-native strategy
- Intended to trade once verification passes
- Currently under validation and isolation
- No impact on Ross or live paths until explicitly enabled

---

## Active Trading Tracks

### Track A — Ross Momentum Live Track (ACTIVE)
- Strategy-driven stock selection enforced
- LIVE_MICRO (1 share) supported with hard risk caps
- Time-of-day aware behaviour
- Mandatory verification commands required
- Adjustments in progress (scanner, modes, adapter)
- Remains the primary live-capable strategy

---

## Implementation Steps in Progress

### Step 3 — Ross Interface Adapter (IN PROGRESS)
- Pure mapping layer: Ross → Strategy Interface
- **No logic change, no behaviour change**
- Adapter only; minimal routing update
- Ross remains live-ready throughout

---

## Stabilisation & Learning

### Stabilisation Phase — COMPLETE (Frozen)
- Scanner market-data alignment
- Watchlist lifecycle governance + observability
- DB auto-recovery and ops summaries
- Mandatory verification commands enforced

### Parallel Learning Epoch — ACTIVE (Isolated)
- Read-only analysis of events and trades
- Scheduled reports and reviews
- Policy proposals only — never auto-applied

---

## Future / Prepared Epochs

### Epoch 6 — PREPARED (Isolated / Non-Executable)
**Long-horizon / Buffett-style strategies**

- Governance bundle present
- Strategy scaffold present
- Runs off-hours / weekends only
- No live or paper execution permitted by default
- Produces Watchlists, Focus Lists, and TradeIntents only
- Must remain isolated from intraday strategies
- Execution requires explicit future governance approval

---

## Frozen Truths (Non-Negotiable)
- Scanner never trades
- Strategies emit **TradeIntent only**
- Strategy Interface normalizes intent; no strategy executes orders
- Risk is the final authority
- Execution obeys mode, caps, and acknowledgements
- Storage is mandatory for all outcomes
- Learning never mutates live logic automatically

---

## Next Actions
- Complete Step 3 (Ross → Interface adapter) with full verification
- Continue Epoch 10 strategy development in isolation
- Proceed with controlled Track A LIVE_MICRO rollout
- Long Horizon Value strategy remains non-executable until explicitly unlocked
