# SYSTEM_ROADMAP_EPOCH_02_TO_COMPLETION

## Status
FROZEN. This file is the authoritative architectural roadmap from Epoch 2 to completion.

## Assumptions
- Phase 24 (Scanner Blueprint & Canonical Output) is complete.
- Scanner contract is locked: Top N gainers → hard gates → Watchlist K (default 15, up to 30) → Focus M (default 3–5, up to 10). Empty outputs are valid.
- `SYSTEM_CONSTITUTION.md` is immutable law.
- `README.md` is descriptive, not prescriptive.
- `SYSTEM_STATE.md` is the only file reflecting current progress.

## Epoch 1 — Foundations & Market Perception
Status: COMPLETE (Phases 1–24)
Delivered: Scanner, data contracts, explainability, deterministic market perception.

## Epoch 2 — Decision Intelligence
Goal: Turn market opportunities into trade intent (no execution).
Phases:
- Phase 25: Strategy Engine Canonical Model
- Phase 26A: Pattern Detection Contracts
- Phase 26B: Ross Core Pattern Implementation
- Phase 26C: Candlestick Library Implementation
- Phase 27: Pattern Aggregation & Conflict Resolution
- Phase 28: Entry/Exit Intent Modelling
- Phase 29: Strategy Registry & Plug-in Architecture
- Phase 30: Strategy Explainability & Logs

## Epoch 3 — Risk & Execution
Goal: Allow live trading without catastrophic loss.
Phases:
- Phase 31: Risk Engine Live Gate
- Phase 32: Execution Engine (IBKR)
- Phase 33: Stop & Exit Enforcement
- Phase 34: Live-Test Mode & Circuit Breakers

## Epoch 4 — Memory, Learning & Recovery
Goal: Make the system improvable and resilient.
Phases:
- Phase 35: Trade Storage Canonical Schema
- Phase 36: Post-Trade Review Engine
- Phase 37: Recovery & Replay Mode
- Phase 38: Analytics & Feedback Loops

## Epoch 5 — Scaling & Strategy Expansion
Goal: Make the system powerful, not fragile.
Phases:
- Phase 39: Capital Scaling Logic
- Phase 40: Intraday Strategy Expansion (Early Entry, Venue-Aware, Statistical Intraday Momentum)
- Phase 41: Human-in-the-Loop Mode
- Phase 42: Adaptive Regime Logic

## Completion Definition (Epoch 5)
- The system can implement intraday strategies as plugins without touching Scanner/Risk/Execution/Storage contracts.
- Ross Momentum remains the reference implementation; optimisation is evidence-driven and versioned.

## Post-Completion (Future Epoch)
Epoch 6: Fundamental / Buffett-style Investing using the same OS with different data cadence and isolated modules.
