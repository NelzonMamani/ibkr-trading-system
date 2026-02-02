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

Run Mode	Market Data	Trade Intents	Execution
READ_ONLY	Live (IBKR)	Allowed	Hard-blocked
PAPER	Live / Simulated	Allowed	Simulated only
LIVE	Live (IBKR)	Allowed	Allowed (risk-governed)

⚠️ SIM exists only for testing and replay and is not considered a trading mode.

Explicitly Removed Concepts

The following are not run modes:

LIVE_MICRO

LIVE_ONE_SHARE

LIVE_READ_ONLY

These are now modeled exclusively as risk profiles or execution constraints, not runtime modes.

3. RISK GOVERNANCE MODEL

Execution eligibility is determined by Risk Engine decisions, not strategies.

Risk evaluation considers:

Run mode

Strategy-specific locks

Risk profile limits

Circuit breakers

Data quality

System health

Risk decisions are:

Deterministic

Logged

Auditable

Explainable via reason codes

4. STRATEGY MATRIX (AUTHORITATIVE)
4.1 Ross Momentum Strategy

Purpose: Intraday momentum trading

Mode	Behavior
READ_ONLY	Scans, selects, emits intents (no execution)
PAPER	Full simulated trading
LIVE	Full live trading (risk-governed)

Status:
✅ Fully implemented
✅ Execution-enabled
✅ Production-ready (pending ongoing tuning)

4.2 Statistical Intraday Momentum

Purpose: Quantitative intraday continuation / reversion

Mode	Behavior
READ_ONLY	Signal generation only
PAPER	Full simulated trading
LIVE	Full live trading (risk-governed)

Status:
✅ Fully implemented
✅ Execution-enabled
⚠️ Still undergoing calibration and validation

4.3 Long Horizon Value Strategy (Epoch 6)

Purpose: Multi-month / multi-year fundamental value investing

Hard Policy Locks (Non-Negotiable)

Market-Closed Only

Strategy will not run during PRE or RTH sessions

Enforced at runner level

Execution Lock in LIVE

LIVE mode may emit TradeIntents

Execution is hard-blocked by Risk Engine

Manual or future explicit override is required to trade live

Mode Behavior
Mode	Behavior
READ_ONLY	Universe discovery, valuation, focus list, reports
PAPER	Simulated buying, allocation, compounding
LIVE	TradeIntents emitted, execution blocked by policy
Risk Enforcement

LIVE execution blocked with reason code:
STRATEGY_READ_ONLY_EXECUTION_LOCK

Block events are emitted and logged

No silent failures

Status:
🟡 Pipeline scaffold implemented
🟡 Governance and safety locks complete
🟡 Execution intentionally disabled by policy

5. EXECUTION SAFETY GUARANTEES

The system guarantees:

No broker orders are sent in READ_ONLY

No strategy can bypass Risk Engine

Long Horizon Value cannot accidentally trade live

All execution paths are logged

All blocks produce explicit reason codes

There are no implicit permissions anywhere in the system.

6. CURRENT DEVELOPMENT FOCUS

Active work is ongoing in:

Scanner correctness & alignment

Statistical strategy calibration

Long Horizon Value pipeline completion

Risk profile tuning

Observability & diagnostics

No further strategies will be allowed to trade live until:

PAPER validation passes

Risk thresholds are verified

Execution audit trails are complete

7. CONSTITUTIONAL NOTES

This document reflects actual enforced behavior, not intent.

Any deviation requires:

Code change

Test coverage

Explicit SYSTEM_STATE update

END OF SYSTEM_STATE.md