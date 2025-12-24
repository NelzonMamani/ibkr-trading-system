🔁 02_SYSTEM_FLOW_CANONICAL.md

Canonical End-to-End System Flow — Trading System Truth

PURPOSE OF THIS DOCUMENT

This document defines the one and only authoritative system flow for the trading system.

It answers:

What happens first?

What happens next?

What happens every cycle?

What happens when things go wrong?

There are no alternatives, shortcuts, or variants in this file.

If a future design contradicts this flow, the design is wrong.

SYSTEM PHILOSOPHY (ONE SENTENCE)

The system continuously observes the market, explains what it sees, decides cautiously, executes only when allowed, and records everything for learning and recovery.

HIGH-LEVEL FLOW OVERVIEW
BOOTSTRAP
→ ORCHESTRATOR LOOP
   → SCANNER
   → PATTERNS / STRATEGY
   → RISK
   → EXECUTION
   → STORAGE
→ REPEAT OR SAFE STOP


This flow is strict, sequential, and non-overlapping.

1️⃣ BOOTSTRAP PHASE (SYSTEM STARTUP)
Objective

Safely initialise the system and verify readiness before any trading logic runs.

Steps

Load configuration (mode, risk limits, symbols, environment).

Initialise logging and runtime context.

Instantiate all system modules:

Core Orchestrator

Market Scanner

Pattern Detection Engine

Strategy Runner (Ross Momentum by default)

Risk Engine

Execution Engine

Storage Engine

Perform health checks:

Time/session awareness

Broker connectivity readiness

Data availability expectations

Transition control to the Orchestrator.

Guarantees

No market interaction occurs before bootstrap completes.

Failures here prevent the system from entering the loop.

2️⃣ ORCHESTRATOR LOOP (SYSTEM HEARTBEAT)
Objective

Run the system in controlled, repeatable cycles.

Rules

Cycles never overlap.

Each cycle follows the same order.

A cycle may be skipped or delayed if health degrades.

Cycle Frequency

Session-aware (PRE / REGULAR / AFTER).

Human-paced in early phases.

Configurable later.

3️⃣ SCANNER PHASE (OBSERVATION)
Objective

Reduce the full market universe into a small set of explainable candidates.

Inputs

Market data

Volume & liquidity metrics

News metadata (if available)

Session context

Actions

Filter the universe (price, liquidity, exchange).

Detect momentum context (gaps, RVOL, volume spikes).

Score and rank symbols.

Track rank changes across cycles.

Outputs

Human-readable scanner prints (explanatory).

Structured scanner results for downstream modules.

Key Rule

❌ Scanner does not detect entry patterns.
❌ Scanner does not place trades.

4️⃣ PATTERNS & STRATEGY PHASE (INTERPRETATION)
Objective

Interpret scanner candidates into trade intent or neutrality.

Pattern Detection Engine

Evaluates each candidate independently.

Detects predefined patterns (Ross Momentum first).

Produces structured PatternResult objects.

Explains detections and rejections.

Strategy Runner

Consumes pattern results.

Applies strategy-specific rules.

Produces one of:

LONG intent

SHORT intent

NEUTRAL (no trade)

Outputs

Trade intent (or explicit neutrality).

Full rationale for decisions.

Key Rule

❌ No orders are placed here.
❌ No position sizing occurs here.

5️⃣ RISK PHASE (PERMISSION)
Objective

Protect capital and system integrity.

Inputs

Trade intent

Account state

Symbol context

System health

Actions

Validate risk rules.

Enforce circuit breakers.

Compute max allowed position size.

Block unsafe trades with explanation.

Outputs

ALLOW / BLOCK / ALLOW_WITH_CONSTRAINTS

Risk rationale text

Risk flags

Key Rule

✅ Risk decisions are final.
❌ No module may bypass Risk.

6️⃣ EXECUTION PHASE (ACTION)
Objective

Accurately and safely convert approved intent into broker orders.

Inputs

Risk-approved trade intent

Order parameters

Broker connectivity state

Actions

Submit orders to IBKR (TWS).

Track order lifecycle (submitted, filled, partial, rejected).

Manage stops when instructed.

Outputs

Execution status updates

Fill details

Execution rationale

Key Rule

❌ Execution does not invent trades.
❌ Execution does not override risk.

7️⃣ STORAGE PHASE (MEMORY)
Objective

Persist everything for learning, auditing, and recovery.

What Is Stored

Scanner snapshots

Pattern detections

Trade intents

Risk decisions (including blocked trades)

Execution results

Errors and recovery events

Outputs

Durable trade records

Confirmation or storage error logs

Key Rule

❌ Nothing important is dropped.
❌ Silent failure is forbidden.

8️⃣ END OF CYCLE
Actions

Orchestrator logs cycle summary.

Health is re-evaluated.

System decides:

Continue

Pause

Safe stop

Then the next cycle begins.

9️⃣ ERROR & RECOVERY FLOW (ANY PHASE)
Principles

Errors are expected.

Recovery is deliberate.

Learning is preserved.

Behaviour

Errors are logged with context.

Recovery actions are taken when possible.

If safety is compromised:

Trading stops

System remains observable

10️⃣ NON-NEGOTIABLE FLOW RULES

The flow order never changes.

Each phase has one responsibility.

No phase performs another phase’s job.

Every decision is explainable.

Every outcome is stored.

STATUS

Phase: PHASE 1 — System Blueprint

Document Role: Canonical System Truth

Next Step: Create 03_MODULE_DEPENDENCY_MAP.md

NEXT ACTION

When ready, say:

“Create 03_MODULE_DEPENDENCY_MAP.md”

This will lock down who depends on whom, preventing architectural drift later.