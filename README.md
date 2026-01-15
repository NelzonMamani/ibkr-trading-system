# ibkr-trading-system

A governed, modular trading operating system designed for **safe, deterministic, explainable** automation of intraday strategies with Interactive Brokers (IBKR) as the primary venue.

## What this system is
- A research-grade trading OS with explicit governance and safety controls
- A deterministic market perception + decision intelligence pipeline
- A platform designed to support multiple strategy families via plug-ins
- An auditable system with event capture, storage, and replay pathways

## What this system is not
- Not a black-box trading bot
- Not an HFT engine
- Not an execution system that can route orders by default

## Governance model (read this first)
The repository is governed by a strict hierarchy:

1. `SYSTEM_CONSTITUTION.md` — immutable law  
2. `SYSTEM_ROADMAP_EPOCH_02_TO_COMPLETION.md` — frozen plan  
3. `SYSTEM_STATE.md` — current truth  
4. `EPOCH_XX_*_GOVERNANCE.md` — epoch scope rules  
5. `PHASE_XX_*.md` — phase deliverables and requirements  

`README.md` is descriptive only and does not override governance.

## Current status (authoritative summary)
- Epoch 1 — Market Perception: COMPLETE
- Epoch 2 — Decision Intelligence: COMPLETE
- Epoch 3 — Risk & Execution: COMPLETE

## Reference strategy
The initial reference implementation is **Ross Cameron-style Retail Confirmation Momentum**.
The architecture is strategy-agnostic and is intended to support additional intraday strategies (and later, long-horizon fundamentals) without redesign.

## Repository structure (high level)
- `src/scanner/` — market perception, gating, watchlists/focus lists, enrichment
- `src/strategies/` — Epoch 2 strategy plug-ins and pattern/candle evidence
- `src/strategy/` — legacy strategy runner components (being governed and consolidated over time)
- `src/risk/`, `src/execution/` — risk and execution engines (must remain gated by governance)
- `src/core/` — orchestrator, events, runtime controls
- `tests/` — contract and safety tests

## Safety posture
Execution is **off by default**. Any live trading capability must be explicitly enabled under the rules of the active epoch governance and must pass safety self-tests.

---
For the authoritative current plan and progress, read `SYSTEM_STATE.md` and the active epoch governance file.
