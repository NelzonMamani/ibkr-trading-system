# ibkr-trading-system — Public Charter

## Purpose
This repository contains a modular, live-capable **Trading OS** designed to:
- Scan the US equity market (NYSE / NASDAQ / AMEX)
- Produce a tradable **Watchlist** and **Focus List**
- Generate **TradeIntent** (never orders)
- Enforce risk, safety, and execution guards
- Execute via IBKR **only when explicitly allowed**
- Persist all decisions for audit, replay, and learning

## Governance & Safety (Non‑Negotiable)
- Scanner observes, never trades
- Scanner universe is policy‑driven; `SCANNER_SYMBOLS` is **testing override only**
- Strategies emit **intent only**
- Strategy intent is normalized via a **Strategy Interface**
- Risk is the **final authority**
- Execution is guarded by **mode**, **caps**, and **explicit acknowledgements**
- Storage is mandatory for all outcomes
- Deterministic, explainable behaviour is required at every layer

## Architecture (High Level)
Scanner → Strategy (Intent) → Interface (Normalization) →
Portfolio Governance (Registry / Arbitration / Capital Allocation) →
Risk → Execution → Storage

## Project Status
- Epoch 4: Scanner contract — **FROZEN**
- Epoch 5: Trading OS core — **FROZEN**
- Epoch 9: Strategy Portfolio Governance (interface, registry, arbitration) — **IMPLEMENTED / SAFE**
- Epoch 10: Statistical Intraday Momentum (interface‑native strategy) — **IN PROGRESS**
- Track A: Ross Momentum LIVE_MICRO rollout — **ACTIVE**
- Stabilisation: scanner, DB, health, observability — **COMPLETE**
- Parallel Learning Epoch — **ACTIVE (isolated, proposal‑only)**
- Epoch 6 (Buffett / long‑horizon) — **FUTURE (isolated)**

## Operating Modes
- SIM
- LIVE_READ_ONLY
- PAPER
- LIVE_MICRO (1 share, capped risk, explicit ACK required)

## Entry Points
- `RUNBOOK.md`
- `SYSTEM_STATE.md`
- `for_track_A/`
- `python -m src.learning.cli --help` (parallel learning reports/proposals)

## Verification (Statistical Intraday Momentum)
- `python -m src.main --strategy statistical_intraday_momentum --mode PAPER --readiness-check`
- `.\VERIFY_STATISTICAL_ALL_MODES.ps1` (PowerShell)

## Contribution Rules
- Respect frozen contracts and epochs
- No silent changes to live logic
- New strategies must conform to the Strategy Interface
- Learning may propose changes, **never auto‑apply**
