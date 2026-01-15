# ibkr-trading-system — Public Charter (README)

## Purpose
This repository contains a **modular, live-testable trading system** (“Trading OS”) designed to:
- Scan the US equity market (NYSE/NASDAQ/AMEX)
- Produce a **tradable watchlist** and a smaller **focus list**
- Generate **strategy signals as intent** (not orders)
- Enforce **risk gating** and **circuit breakers**
- Execute via **IBKR/TWS** only when approved
- Persist full context for **audit, review, and improvement**

The first-class strategy is **Ross Cameron-style Momentum**. The architecture is **strategy-agnostic** so additional strategies can be added without redesign.

## Non-Negotiables (Governance)
### Strategy Boundaries
- **Scanner** watches and explains; it does not trade.
- **Patterns/Strategy** produce **TradeIntents**; they do not place orders.
- **Risk** is the final authority; it may block anything and must explain why.
- **Execution** submits/modifies/cancels broker orders; it does not invent signals.
- **Storage** is mandatory; every attempt must be persisted (including blocked/failed).

### Safety Philosophy (Live-First)
- The system is designed to be **live-testable safely**.
- Phase-1 live testing starts with **LIVE_1SHARE** (1-share mode) under strict limits.
- Circuit breakers (daily loss, max trades, connectivity/data failures) must stop trading safely.

### Determinism & Explainability
- Identical inputs should yield identical decisions (deterministic behaviour).
- Every decision must be explainable via teacher-style logs and stored rationale.

## Market Scope
- **US equities only** on **NYSE/NASDAQ/AMEX**.
- Broker connectivity/execution via **IBKR TWS**.
- Python is the executable language for trading logic.

## Operating Modes
The system must run in three explicit modes:
- **SIM**: simulation mode (no broker orders)
- **READONLY**: live data observation (no broker orders; logs “would place”)
- **LIVE_1SHARE**: live execution bounded to 1-share sizing (risk still gates everything)

## Epoch Model (Project Roadmap)
### Epoch 4 — Scanner Contract Finalisation (Closed)
Epoch 4 is complete. The scanner contract is frozen as:
**Top N gainers → hard gates → Watchlist K → Focus M**  
- Default **K=15** (configurable up to 30)  
- Default **M=3–5** (configurable up to 10)  
- **Empty watchlists are valid** behaviour and must be explained (drop reasons).

### Epoch 5 — System Completion & Hardening (Active)
Epoch 5 completes the full Trading OS for the intraday momentum strategy class:
- Packaging/import stability and governance anchoring
- End-to-end orchestration: Scanner → Patterns → Strategy → Risk → Execution → Storage
- Operator-grade console outputs (clear watchlist and 3–5 focus symbols)
- Minimal but real tests (smoke + contract) to prevent regressions
- Robust degradation and safe-stop on critical health/data conditions

### Epoch 6 — Long-Horizon / Buffett-Style (Isolated, Future)
Epoch 6 is a **separate strategy class** focused on long-horizon compounding and quality fundamentals.
It is **intentionally isolated** from intraday trading logic (different cadence/data), while sharing the same OS governance principles.

## Getting Started
See:
- `RUNBOOK.md` for exact run commands and operational guidance
- `SYSTEM_STATE.md` for the current authoritative project status and “what is frozen”

## Contribution Rules (for humans or agents)
- Make changes in small, verifiable increments.
- Respect module boundaries.
- Do not expand scope without updating `SYSTEM_STATE.md` and the relevant requirements docs.
- Any new behaviour must include:
  - deterministic logic
  - clear logs
  - persisted context
