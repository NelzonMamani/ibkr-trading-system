♻️ 04_ERROR_AND_RECOVERY_CONTRACTS.md

Phase 2 — Canonical Error & Recovery Contracts

PURPOSE OF THIS DOCUMENT

This document defines how errors are represented, surfaced, and recovered from at the interface level.

It ensures:

Failures are visible

Recovery is deliberate

State is never silently corrupted

Live trading remains safe

This document defines contracts, not implementations.

CORE PHILOSOPHY

Failure is expected.
Silence is not.

A system that fails loudly and recovers deliberately is safer than one that pretends nothing happened.

ERROR CLASSIFICATION (AUTHORITATIVE)

All errors must be classified into one of the following categories:

DATA_ERROR
STRATEGY_ERROR
RISK_ERROR
EXECUTION_ERROR
BROKER_ERROR
STORAGE_ERROR
SYSTEM_ERROR


No custom categories are allowed without updating this document.

ERROR CONTRACT (GENERIC)

Every error surfaced by any module must include:

error_type — one of the categories above

error_code — short stable identifier

error_message — human-readable explanation

module_name

timestamp

severity — WARNING / ERROR / CRITICAL

recoverable_flag

This structure may be embedded in:

return objects

exception wrappers

TradeRecord fields

MODULE-SPECIFIC ERROR & RECOVERY CONTRACTS
1️⃣ Scanner

Expected Errors

Data source unavailable

Stale market data

Partial symbol data

Recovery Behaviour

Log warning

Skip affected symbols

Continue scanning

Unrecoverable Conditions

All data sources unavailable → escalate to Core Engine

2️⃣ Pattern Engine

Expected Errors

Missing indicators

Invalid candle data

Recovery Behaviour

Mark pattern as NOT detected

Flag data quality issue

Continue evaluation

Unrecoverable Conditions

Corrupted input data → stop evaluation for symbol only

3️⃣ Strategy Runner

Expected Errors

Conflicting high-confidence patterns

Missing pattern context

Recovery Behaviour

Produce neutral decision

Log rationale

Continue cycle

Unrecoverable Conditions

Invalid TradeIntent construction → abort intent creation

4️⃣ Risk Engine

Expected Errors

Account data unavailable

Risk thresholds undefined

Recovery Behaviour

BLOCK trade

Log explicit rationale

Unrecoverable Conditions

Risk engine state corrupted → halt trading

5️⃣ Execution Engine

Expected Errors

Broker rejection

Order submission failure

Partial fills

Recovery Behaviour

Capture broker error codes

Update ExecutionResult

Inform Storage

Unrecoverable Conditions

Broker connection lost mid-trade → escalate to Core Engine

6️⃣ Storage Engine

Expected Errors

Database unavailable

Partial write failure

Recovery Behaviour

Retry write

Log error

Flag TradeRecord as incomplete

Unrecoverable Conditions

Persistent storage failure → halt system

7️⃣ Core Orchestrator

Expected Errors

Module non-responsiveness

Health degradation

Recovery Behaviour

Restart affected module

Throttle cycles

Enter safe-stop if needed

Unrecoverable Conditions

Multiple critical module failures → full system halt

RECOVERY MODES (EXPLICIT STATES)

The system supports the following recovery modes:

NORMAL
DEGRADED
SAFE_STOP
RECOVERY

Mode Definitions

NORMAL — full functionality

DEGRADED — limited but safe operation

SAFE_STOP — no new trades, manage exits only

RECOVERY — rebuilding state after failure

The current mode must always be logged.

RECOVERY LOGGING CONTRACT

Every recovery action must log:

Triggering error

Recovery action taken

Result of recovery

Current system mode

Example

[RECOVERY] Entering SAFE_STOP — broker connectivity unstable

TRADE RECORD INTEGRATION

All errors and recovery events must be persisted in TradeRecord:

error history

recovery actions

flags indicating incomplete or unreliable data

This enables:

post-mortem analysis

AI learning

compliance review

NON-GOALS OF THIS DOCUMENT

This document does NOT:

Define retry logic

Define exception classes

Define logging libraries

Only interface-level behaviour.

STATUS

Phase: PHASE 2 — Interface & Contracts

Step: 2.4 — Error & Recovery Contracts

State: COMPLETE

Next Step: Phase 2 Definition of Done

NEXT ACTION

When ready, say:

“Proceed to STEP 2.5 — Phase 2 Definition of Done”

Once that is complete, Codex becomes extremely useful and Phase 3 can begin.