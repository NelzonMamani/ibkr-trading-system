PHASE 4 — Minimal Live-Capable System Step Breakdown (Safety-First)
Purpose of This File

This document defines Phase 4 in the same disciplined way Phase 3 was defined and completed.

Phase 4 is where the system starts to behave like a real trading system, but under strict safety, visibility, and control.

If Phase 3 answered:

“Is the system structurally correct?”

Phase 4 answers:

“Can the system interact with the real world safely?”

Phase 4 — High-Level Objective (Restated)

Transform the Phase-3 skeleton into a minimal live-capable system that:

can run continuously

can consume realistic data

can make permissioned decisions

can stop safely at any time

remains fully explainable

Live-capable ≠ Live-trading
Live-capable means ready, not reckless.

Global Phase-4 Guardrails (Non-Negotiable)

These apply to every step in Phase 4.

✅ Always Required

Explicit run modes (SIM / PAPER / LIVE)

Teaching-style logs

Safe defaults

Deterministic behaviour

Graceful shutdown support

❌ Still Forbidden

Automatic live trading without human confirmation

Strategy complexity

Optimisation

Silent execution paths

“Just test it live” behaviour

STEP 4.1 — Runtime Configuration & Run Modes
Objective

Introduce explicit runtime modes so the system knows how dangerous it is allowed to be.

Concepts Introduced

RUN_MODE = SIM | PAPER | LIVE

Default = SIM

Mode printed at boot

Mode checked before any risky action

Scope

Configuration file or constants

No behaviour change yet

Definition of Done

System prints current run mode

No ambiguity about safety level

STEP 4.2 — Continuous Run Loop & Graceful Shutdown
Objective

Move from “run once” to run continuously in a controlled loop.

Concepts Introduced

Time-based loop

Sleep interval

KeyboardInterrupt handling

Clean exit logging

Scope

Orchestrator loop only

No data logic

Definition of Done

System runs continuously

Ctrl+C shuts it down cleanly

No orphaned state

STEP 4.3 — Data Source Abstraction (Simulated First)
Objective

Introduce realistic data flow without touching live brokers.

Concepts Introduced

Data source interface

Simulated / mock market data

Deterministic outputs for learning

Scope

New data provider abstraction

Scanner consumes simulated data

Definition of Done

Scanner receives non-empty mock data

Logs explain data origin

STEP 4.4 — Risk Engine Activation (Minimal)
Objective

Turn Risk Engine into an active gatekeeper, even if it blocks everything.

Concepts Introduced

“No trade allowed” default

Explicit block reasons

Risk decision objects

Scope

Risk Engine only

No execution yet

Definition of Done

Risk engine actively blocks actions

Logs explain why

STEP 4.5 — Paper-Safe Execution Stub
Objective

Allow the system to simulate execution safely.

Concepts Introduced

Paper execution acknowledgements

Fake order IDs

No broker connectivity

Scope

Execution Engine only

No IBKR yet

Definition of Done

Execution stage produces simulated results

No external side effects

STEP 4.6 — Observability & Log Discipline Upgrade
Objective

Ensure Phase-4 behaviour is fully understandable from logs alone.

Concepts Introduced

Consistent log prefixes

Clear decision narratives

Error vs info separation (still simple)

Scope

Logging patterns only

No framework changes yet

Definition of Done

Logs explain what and why

Easy to follow full cycle in console

STEP 4.7 — Phase 4 Validation & Freeze
Objective

Formally freeze Phase 4 once it is safe and trustworthy.

Validation Checklist

Continuous run works

Shutdown is clean

No live risk

All actions gated by mode

Logs explain everything

Definition of Done

Phase 4 marked frozen

Ready to enter Phase 5 (strategy implementation)

Phase 4 Status Tracking

Phase: PHASE 4 — Minimal Live-Capable System

Status: PLANNED (not started)

Current Step: STEP 4.1 — Runtime Configuration & Run Modes

Teaching Note (Important)

Phase 4 is where discipline matters most.

Most trading systems fail here because:

safety checks are skipped

modes are unclear

developers “just try live”

You will not make those mistakes.

Next File to Create
13_PHASE_4_STEP_4_1_CODEX_INSTRUCTIONS.md


This file will contain:

exact Codex instructions

allowed files

forbidden actions

expected runtime behaviour

Your next reply (one line)

Please reply with:

“Proceed — create STEP 4.1 Codex instructions”

We continue exactly as before — calmly, safely, and professionally.