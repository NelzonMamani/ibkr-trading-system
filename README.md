# ibkr-trading-system — Public Charter

## Purpose
This repository contains a modular, live-capable Trading OS designed to:
- Scan the US equity market (NYSE / NASDAQ / AMEX)
- Produce a tradable watchlist and focus list
- Generate TradeIntent (never orders)
- Enforce risk, safety, and execution guards
- Execute via IBKR only when explicitly allowed
- Persist all decisions for audit and learning

## Governance & Safety
- Scanner observes, never trades
- Scanner universe is policy-driven; SCANNER_SYMBOLS is a testing override only
- Strategies emit intent only
- Risk is final authority
- Execution is guarded by mode and caps
- Storage is mandatory
- Deterministic, explainable behaviour required

## Project Status
- Epoch 4: Scanner contract — frozen
- Epoch 5: Trading OS — frozen
- Track A: Ross Momentum LIVE_MICRO rollout — active
- Stabilisation: scanner, DB, health, observability — complete
- Parallel Learning Epoch — active (isolated, proposal-only)
- Epoch 6 (Buffett) — future

## Operating Modes
- SIM
- LIVE_READ_ONLY
- LIVE_MICRO (1 share, capped risk)

## Entry Points
- RUNBOOK.md
- SYSTEM_STATE.md
- for_track_A/
- `python -m src.learning.cli --help` (parallel learning reports/proposals)

## Contribution Rules
- Respect frozen contracts
- No silent changes
- Learning may propose, never auto-apply
