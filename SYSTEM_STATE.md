SYSTEM_STATE.md

IBKR Trading System — Authoritative Runtime State

Last Updated: 2026-02-02
Status: ACTIVE DEVELOPMENT — LIVE-SAFE
Authority Level: Canonical (supersedes prior SYSTEM_STATE versions)

1. SYSTEM OVERVIEW

The IBKR Trading System is a multi-strategy, multi-mode trading platform designed with strict separation between:

Data acquisition
Strategy decision logic
Risk governance
Execution routing

The system enforces safety-first execution guarantees and supports multiple strategies operating concurrently under a unified orchestration layer.

2. CANONICAL RUN MODES (LOCKED)

The system operates under exactly three canonical run modes:

Run Mode | Market Data | Trade Intents | Execution
READ_ONLY | Live (IBKR) | Allowed | Hard-blocked
PAPER | Live / Simulated | Allowed | Simulated only
LIVE | Live (IBKR) | Allowed | Allowed (risk-governed)

SIM exists only for testing and replay and is not considered a trading mode.

3. RISK GOVERNANCE MODEL

Execution eligibility is determined by Risk Engine decisions, not strategies.

4. STRATEGY MATRIX (AUTHORITATIVE)

4.1 Ross Momentum Strategy
(Status unchanged)

4.2 Statistical Intraday Momentum
(Status unchanged)

4.3 Long Horizon Value Strategy
(Status unchanged)

4.4 Mean Reversion Strategy

Purpose: Intraday mean reversion and exhaustion-based reversal trading

Mode | Behavior
READ_ONLY | Evaluates scanner facts, emits TradeIntents (no execution)
PAPER | Full simulated trading (pending validation)
LIVE | TradeIntents allowed, execution blocked by Risk Engine

Hard Policy Locks
- LIVE execution disabled until PAPER validation passes
- Must comply with SYSTEM_CONSTITUTION.md
- Non-interference with other strategies enforced

Status:
Implemented
Governance complete
Execution disabled pending PAPER verification

5. EXECUTION SAFETY GUARANTEES
(Unchanged)

6. CURRENT DEVELOPMENT FOCUS
(Unchanged)

7. CONSTITUTIONAL NOTES
(Unchanged)

END OF SYSTEM_STATE.md
