PHASE 3 — Skeleton System Step Breakdown (Teaching-First, Restarted)
Purpose of This File

This document defines the exact steps of Phase 3 in a way that is:

sequential

teachable

auditable

compatible with Codex + GitHub PR workflow

easy to pause, resume, or restart

If at any moment you feel lost, this file is the anchor.

Phase 3 — High-Level Objective (Restated)

Build a fully runnable, multi-module trading system skeleton that:

starts cleanly

runs a full orchestration cycle

shuts down cleanly

teaches how the system works

contains no trading logic

Phase 3 is about structure and flow, not behaviour.

Phase 3 — Allowed vs Forbidden (Global Rules)
✅ Allowed in Phase 3

Python files only

Class definitions

Method signatures

Teaching-style print() logs

Empty lists / None returns

Deterministic, single-cycle execution

Clear module boundaries

❌ Forbidden in Phase 3

Interactive Brokers API usage

Real market data

Indicator calculations

Risk math

Order placement logic

Optimisation or performance tuning

Silent logic (everything must print)

STEP 3.1 — Project Skeleton & Entry Point
Objective

Create a minimal but correct project skeleton that can be executed.

Scope

Folder structure

main.py entry point

No inter-module logic yet

Deliverables

src/main.py

Correct imports

One clean execution path

Definition of Done

python src/main.py runs

Prints boot + shutdown messages

No imports fail

STEP 3.2 — Core Orchestrator Skeleton
Objective

Create the central orchestration flow of the system.

Scope

Core orchestrator class

Single execution cycle

Sequential flow:
Scanner → Patterns → Strategy → Risk → Execution → Storage

Deliverables

core/orchestrator.py

Teaching logs showing system flow

Definition of Done

Orchestrator runs one cycle

All steps print in order

No logic is executed

No external dependencies

STEP 3.3 — Module Skeletons (Individually Valid)
Objective

Ensure every module is valid Python and runnable in isolation.

Modules Covered

Scanner

Pattern Engine

Strategy Runner

Risk Engine

Execution Engine

Storage Engine

Data Models

Scope

Class definitions

Method stubs

Teaching prints

Placeholder returns

Definition of Done

Each module:

imports cleanly

can be instantiated

prints when methods are called

No diff artifacts

No runtime errors

STEP 3.4 — Wire Orchestrator to Module Skeletons
Objective

Connect the orchestrator to all module skeletons.

Scope

Instantiate modules inside orchestrator

Pass placeholder data between them

Maintain strict order

Deliverables

Updated core/orchestrator.py

Definition of Done

Full cycle runs end-to-end

All module methods are invoked

Logs clearly show data flow

No logic, only flow

STEP 3.5 — Skeleton Trade Record & Storage Flow
Objective

Introduce a minimal trade record flow without logic.

Scope

Data model placeholders

Storage engine accepting records

Teaching logs explaining intent

Definition of Done

A TradeRecord object is created

Storage engine acknowledges receipt

No persistence logic yet

STEP 3.6 — Phase 3 Freeze & Validation
Objective

Formally freeze Phase 3 so it never drifts.

Actions

Final review of:

structure

logs

imports

Confirm:

no logic slipped in

everything is teachable

Definition of Done

Phase 3 marked “Frozen”

No further edits allowed without version bump

Ready to enter Phase 4

Canonical Phase 3 Workflow (Reminder)

For every step above:

Define the step clearly (this file)

Generate one Codex instruction

Codex opens a Pull Request

Review on GitHub

Merge

Pull into PyCharm

Run and observe

Only then proceed

Phase 3 Status Tracking

Phase: PHASE 3 — Skeleton System

Mode: Teaching-First

Restarted: Yes

Current Step: STEP 3.1 (about to begin)

Next Action (Explicit)

The next artefact to create is:

05_PHASE_3_STEP_3_1_INSTRUCTIONS.md


This file will contain:

the exact Codex prompt

allowed files

stop conditions

expected PR outcome

Stop Here

Do not proceed to Codex yet until that file exists.

End of file.

When you’re ready, reply with:

“Proceed — create STEP 3.1 Codex instructions”

We will continue calmly, one step at a time.