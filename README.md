# ibkr-trading-system — Public Charter (README)

## Purpose
This repository contains a **modular, deterministic, live-testable trading system** (“Trading OS”) designed to:
- Scan the US equity market (NYSE / NASDAQ / AMEX)
- Produce a **tradable watchlist** and a smaller **focus list**
- Generate **strategy signals as TradeIntent** (never orders)
- Enforce **risk gating, circuit breakers, and execution constraints**
- Execute via **Interactive Brokers (IBKR)** only when explicitly permitted
- Persist full context for **audit, replay, and continuous improvement**

The first-class live strategy is **Ross Cameron–style Momentum**.
The architecture is **strategy-agnostic**, enabling multiple intraday and long-horizon strategies without redesign.

## Governance & Safety (Non-Negotiable)
- Scanner observes and explains — it never trades
- Strategies emit **TradeIntent**, never broker orders
- Risk is the final authority and may veto any intent with rationale
- Execution obeys run-mode and hard constraints
- Storage is mandatory for *all* decisions and outcomes

The system is **live-first but safety-bound**:
- SIM → LIVE_READ_ONLY → LIVE_MICRO → LIVE progression
- Circuit breakers enforce loss, trade count, and system health limits
- Deterministic, explainable behaviour is mandatory in all modes

## Project Status (Authoritative Summary)
- **Epoch 4**: Scanner contract — complete and frozen
- **Epoch 5**: Trading OS core — complete and frozen
- **Track A**: Ross Momentum live track — active, iterative refinement ongoing
- **Adaptive Regime / Microstructure Layer**: planned, governed, pending implementation
- **Epoch 6**: Long-horizon / Buffett-style strategies — future, isolated

## Operating Modes
- **SIM** — deterministic simulation, no broker routing
- **LIVE_READ_ONLY** — live market data, orders blocked
- **LIVE_MICRO** — live execution with strict micro constraints
- **LIVE** — full live execution under governance

## Entry Points
- See `RUNBOOK.md` for canonical run commands
- See `SYSTEM_STATE.md` for the single source of operational truth

## Contribution Rules
- Respect governance hierarchy and frozen contracts
- No silent scope expansion
- All behaviour must be deterministic, logged, and persisted
