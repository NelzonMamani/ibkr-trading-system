🖨️ 03_PRINT_AND_LOGGING_CONTRACTS.md

Phase 2 — Canonical Print & Logging Contracts

PURPOSE OF THIS DOCUMENT

This document defines what must be printed and logged by the system, regardless of implementation details.

It ensures:

Human observability

Teaching-first behaviour

Post-mortem explainability

AI learning traceability

Safe live trading

This document defines what must be logged, not how logging is implemented.

If a decision occurs and is not logged, it is a bug.

CORE LOGGING PHILOSOPHY

Every meaningful decision must explain itself in human language.

Logs are not for machines only.
Logs are runtime documentation for:

the trader

the developer

future AI review

recovery mode

REQUIRED LOG CATEGORIES (AUTHORITATIVE)

All logs must use one of the following standard prefixes:

[BOOT]        — System startup and shutdown
[INFO]        — Informational system state
[DATA]        — Market or data quality observations
[SCAN]        — Scanner outputs and reasoning
[PATTERN]     — Pattern detection decisions
[STRATEGY]    — Trade intent decisions
[RISK]        — Risk approvals or blocks
[ACTION]      — Intent to act (pre-execution)
[EXECUTION]   — Broker interaction results
[STORAGE]     — Persistence results
[RECOVERY]    — Recovery actions
[WARNING]     — Degraded but recoverable state
[ERROR]       — Failures requiring attention


No free-form prefixes are allowed.

MODULE-SPECIFIC LOGGING REQUIREMENTS
1️⃣ Core Orchestrator

Must log:

Cycle start and end

Current session (PRE / REGULAR / AFTER)

Which phase is running

Cycle summary

Example

[INFO] Starting new orchestrator cycle (Session: REGULAR)

2️⃣ Scanner

Must log:

Scan cycle start

Number of symbols evaluated

Why each symbol is included

Why symbols drop out

Data quality issues

Example

[SCAN] NVDA | Gap +12.4%, RVOL 5.8x, Float 7.2M — strong momentum candidate

3️⃣ Pattern Engine

Must log:

Every evaluated pattern

Detection and rejection reasons

Confidence scores

Example

[PATTERN] AAPL | Micro Pullback detected (Confidence: 0.82) — above VWAP, volume dry-up


If not detected:

[PATTERN] AAPL | Bull Flag NOT detected — insufficient consolidation

4️⃣ Strategy Runner

Must log:

Why a TradeIntent was created

Why neutrality was chosen

Conflicts or low confidence

Example

[STRATEGY] TradeIntent created for TSLA (LONG) — ORB + strong volume confirmation

5️⃣ Risk Engine

Must log:

Risk decision (ALLOW / BLOCK)

Exact rule that triggered a block

Position size constraints

Example

[RISK] BLOCK — Spread too wide (0.42 > 0.15 max allowed)

6️⃣ Execution Engine

Must log:

Order submission intent

Broker acknowledgement

Fills, partial fills, rejections

Broker error codes

Example

[EXECUTION] Order submitted (BUY 1 AAPL @ MKT) — IBKR acknowledged

7️⃣ Storage Engine

Must log:

Successful writes

Failed writes

Partial persistence warnings

Example

[STORAGE] TradeRecord stored successfully (trade_id=abc123)

DECISION LOGGING RULE (NON-NEGOTIABLE)

For every decision:

log what was decided

log why

log what data influenced it

If the system chooses not to act, it must still log why.

ERROR & WARNING LOGGING RULES
Errors MUST include:

What failed

Why it likely failed

What will happen next

Example
[ERROR] Market data unavailable for MSFT — switching to fallback provider

RECOVERY LOGGING REQUIREMENTS

Recovery actions must always log:

What was lost

What was rebuilt

Whether state is partial or full

Example

[RECOVERY] Broker connection dropped — reconnecting and resubscribing to open orders

LOGGING VERBOSITY LEVELS (CONCEPTUAL)

INFO — normal operation

WARNING — degraded but safe

ERROR — unsafe, requires attention

Actual implementation (logging library, levels) is deferred.

NON-GOALS OF THIS DOCUMENT

This document does NOT:

Define logging libraries

Define log storage

Define performance optimisation

Only content and intent.

STATUS

Phase: PHASE 2 — Interface & Contracts

Step: 2.3 — Print & Logging Contracts

State: COMPLETE (Canonical Definition)

Next Step: Define error & recovery contracts

NEXT ACTION

When ready, say:

“Proceed to STEP 2.4 — Define error & recovery contracts”

You are progressing exactly as a professional software engineer would.