# ibkr-trading-system — Public Charter (README)

## Purpose
This repository contains a **modular, live-testable trading system** (“Trading OS”) designed to:
- Scan the US equity market (NYSE/NASDAQ/AMEX)
- Produce a **tradable watchlist** and a smaller **focus list**
- Generate **strategy signals as intent** (not orders)
- Enforce **risk gating** and **circuit breakers**
- Execute via **IBKR/TWS** only when approved
- Persist full context for **audit, review, and improvement**

The first-class live strategy is **Ross Cameron–style Momentum**.
The architecture is **strategy-agnostic**, allowing additional strategies without redesign.

## Governance & Safety (Non-Negotiable)
- Scanner observes and explains — it never trades
- Strategies emit **TradeIntent**, never broker orders
- Risk is final authority and may block anything with rationale
- Execution submits broker orders only when approved
- Storage is mandatory for *all* decisions and outcomes

The system is **live-first but safety-bound**:
- SIM → READONLY → LIVE_1SHARE progression
- Circuit breakers enforce daily loss, trade count, and health limits
- Deterministic, explainable behaviour is mandatory

## Project Status
- **Epoch 4**: Scanner contract — complete and frozen
- **Epoch 5**: Trading OS completion — complete and frozen
- **Track A**: Ross Momentum live execution track — active
- **Epoch 6**: Long-horizon / Buffett-style strategies — future, isolated

## Operating Modes
- SIM — simulation only
- READONLY — live data, no orders
- LIVE_1SHARE — live execution, strictly bounded

## Entry Points
- See `RUNBOOK.md` for canonical run commands
- See `SYSTEM_STATE.md` for authoritative operational status

## Contribution Rules
- Respect module boundaries and frozen contracts
- Small, verifiable changes only
- Any new behaviour must be deterministic, logged, and persisted
