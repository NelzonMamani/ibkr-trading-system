PHASE 4 — Minimal Live-Capable System (Overview & Guardrails)
Purpose

Phase 4 transitions the project from a pure skeleton to a minimal live-capable system.

“Live-capable” does not mean aggressive trading or full automation.
It means the system can safely interact with the real world (or paper mode) in a strictly controlled, observable way.

Phase 4 is about safety, realism, and discipline.

Phase 4 — High-Level Objective

Introduce real behaviour into the system in the smallest possible steps while preserving:

safety

explainability

recoverability

teaching value

At the end of Phase 4, the system should be able to:

run continuously (not just one cycle)

connect to realistic data sources (simulated or paper)

enforce basic risk gates

log everything clearly

still be safe to stop, restart, and inspect

How Phase 4 Is Different from Phase 3
Phase 3 (Completed)

Shape only

No behaviour

One cycle

No side effects

Phase 4 (Starting)

Minimal behaviour

Multiple cycles (looping)

Controlled side effects

Still no real trading risk

Think of Phase 4 as:

“A system that could trade, but mostly watches and explains.”

Core Principles of Phase 4 (Non-Negotiable)

Safety First

Default to paper / simulation

Explicit flags for any live interaction

Fail closed, not open

One Change at a Time

Each step adds exactly one new capability

No stacking changes

Everything Is Observable

No silent logic

Logs explain why, not just what

Recovery Is Always Possible

System can be stopped mid-run

Restart does not corrupt state

Errors are logged, not hidden

Teaching Continues

Phase 4 still teaches

Logs remain verbose

Comments remain explanatory

Phase 4 — What Is Now ALLOWED

Configuration files (read-only at first)

Continuous run loop (time-based)

Simulated or paper data sources

Basic risk checks (e.g. “do nothing” rules)

Structured logging (still simple)

Graceful shutdown handling

Phase 4 — What Is Still FORBIDDEN

Full automation without human visibility

Aggressive position sizing

Optimisation

Strategy complexity

Multiple strategies at once

Unbounded loops without sleep

Silent execution paths

Phase 4 — Planned Sub-Steps (Preview)

These steps will each have their own instruction file, just like Phase 3.

STEP 4.1 — Runtime Configuration & Modes

Introduce:

RUN_MODE (SIM / PAPER / LIVE)

SAFE defaults

No behaviour change yet

STEP 4.2 — Controlled Run Loop

Replace “run once” with:

timed loop

clean shutdown handling

Still placeholder behaviour

STEP 4.3 — Data Source Abstraction (Minimal)

Introduce:

mock / simulated market data

clear data contracts

No IBKR yet

STEP 4.4 — Risk Engine Activation (Minimal)

Introduce:

“do nothing unless allowed” rules

hard blocks

Still no execution

STEP 4.5 — Paper-Safe Execution Stub

Allow:

simulated orders

paper acknowledgements

No live orders

Phase 4 Entry Conditions (All Met)

You are allowed to enter Phase 4 because:

Phase 3 is frozen

System structure is trusted

Workflow discipline is proven

You can:

instruct Codex correctly

review PRs

merge safely

pull and run locally

This is exactly when Phase 4 should begin.

Phase 4 Exit Condition (Preview)

Phase 4 will be considered complete when:

The system can run continuously without crashing

All external interactions are gated

Every decision is explainable

Turning “LIVE” on requires an explicit, conscious action

You feel confident reading logs and understanding behaviour

Teaching Note (Important)

Many systems fail because developers:

add behaviour too early

trust code before understanding it

skip observability

You are doing the opposite.

Phase 4 will feel slower — that’s a feature, not a bug.

Current Status

Phase: PHASE 4 — Minimal Live-Capable System

Status: ENTERED (overview complete)

Next Action: Define Phase 4 steps in detail

Next File to Create
12_PHASE_4_STEP_BREAKDOWN.md


This will mirror what we did in Phase 3:

exact steps

exact objectives

exact guardrails

zero ambiguity

Your next reply (one line)

Please reply with:

“Proceed — create Phase 4 step breakdown”

We will continue with the same calm, professional rhythm.