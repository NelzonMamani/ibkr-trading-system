# SYSTEM_STATE — Authoritative Project Status
Last updated: 2026-01-18

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
Trading OS end-to-end pipeline complete:
Scanner → Patterns → Strategy → Risk → Execution → Storage
Includes determinism, explainability, and safety enforcement.

### Track A — Ross Momentum Live Track (ACTIVE)
Track A operationalizes Ross Momentum for live trading:
- Time-of-day aware policies (morning / mid / late)
- Micro-pullback, breakout, and continuation families
- Topping, exhaustion, and pause logic enforced
- Paper → LIVE_1SHARE progression required
- Manual verification completed post-Epoch 5

### Epoch 6 — FUTURE (Isolated)
Long-horizon / Buffett-style strategies.
No shared cadence or data with intraday trading.

---
## Frozen Truths (Non-Negotiable)
- Scanner never trades
- Strategy emits TradeIntent only
- Risk is final authority
- Execution obeys mode and constraints
- Storage is mandatory for all outcomes

---
## Next Action
Proceed with Track A phased live rollout per `for_track_A/PHASE_INDEX.md`.

## Track A Authority Note
Track A strategy integrations are authoritative under `src/strategies/*`.
Legacy adapters in `src/strategy/*` remain for compatibility only and should
not be used for new Ross Momentum wiring.
