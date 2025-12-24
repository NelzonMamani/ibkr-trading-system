🗺️ 01_DEVELOPMENT_ROADMAP.md

End-to-End Development Plan — From Intent to Live Trading System

PURPOSE OF THIS DOCUMENT

This roadmap defines the entire lifecycle of the project, from first intent to a scalable, live-capable trading system.

Its goals are to:

Clearly define development phases

Specify what happens in each phase

Prevent phase mixing

Provide entry and exit criteria for every phase

Ensure you always know where you are and what comes next

If you are unsure what to work on, this file is the answer.

GLOBAL DEVELOPMENT PHASES (AUTHORITATIVE)

The project proceeds strictly through the following phases:

PHASE 0 — Intent Capture
PHASE 1 — System Blueprint
PHASE 2 — Interface & Contracts
PHASE 3 — Skeleton System (No Logic)
PHASE 4 — Minimal Live-Capable System
PHASE 5 — Strategy Expansion
PHASE 6 — Optimisation & Scaling


You may only be actively working in one phase at a time.

PHASE 0 — INTENT CAPTURE ✅ (COMPLETED & FROZEN)
Purpose

Capture what you were trying to build before implementation.

Outputs

Vision documents

Strategy specifications (Ross Momentum)

Module requirements

Governance, doctrine, recovery protocols

Learning and storage requirements

Location

dev_docs_00/

Rules

Read-only

Referenced, not edited

Historical truth

Exit Criteria

✔ All major intentions documented
✔ No ambiguity about goals or constraints

PHASE 1 — SYSTEM BLUEPRINT 🧠 (CURRENT PHASE)
Purpose

Create a single, reconciled understanding of the system that will now be built.

This phase answers:

What exactly are we building?

How does it work end-to-end?

In what order will we build it?

How do humans and AI collaborate safely?

Outputs

Located in dev_docs_01/:

README.md (current state & rules)

01_DEVELOPMENT_ROADMAP.md (this file)

02_SYSTEM_FLOW_CANONICAL.md

03_MODULE_DEPENDENCY_MAP.md

04_CODEX_OPERATING_MODEL.md

05_DEFINITION_OF_DONE.md

Allowed

Documentation

Clarification

Reconciliation of ideas

Explicit decisions

Not Allowed

Writing code

Creating skeletons

Using Codex for implementation

Performance discussions

Exit Criteria

✔ One authoritative system flow
✔ One authoritative development order
✔ Clear AI usage rules
✔ Clear “done” definition

PHASE 2 — INTERFACE & CONTRACTS 📐
Purpose

Define how modules talk to each other, without logic.

This phase creates:

function signatures

data models

input/output contracts

print/log contracts

error and recovery contracts

Outputs

Interface definitions

Contract documents

Data model specifications

Allowed

Defining inputs/outputs

Defining return structures

Defining failure modes

Not Allowed

Implementing logic

Connecting to IBKR

Trading decisions

Exit Criteria

✔ Every module has explicit contracts
✔ No ambiguity about inputs/outputs
✔ All contracts testable

PHASE 3 — SKELETON SYSTEM 🦴 (NO LOGIC)
Purpose

Create a fully wired system structure with no real trading logic.

This phase proves:

imports work

modules connect

the system starts and runs

logs appear correctly

Outputs

Python skeleton files (*_v01.py)

Placeholder methods

Demonstration runs

Allowed

File creation

Class scaffolding

Logging stubs

Not Allowed

Strategy logic

Risk enforcement

Live trading

Exit Criteria

✔ System runs end-to-end
✔ No runtime errors
✔ All modules callable

PHASE 4 — MINIMAL LIVE-CAPABLE SYSTEM ⚠️
Purpose

Introduce real behaviour with minimal risk.

This is the first phase that:

touches IBKR

submits orders

trades with 1 share only

Outputs

Live-capable scanner (minimal)

Live-capable execution (basic)

Risk gate (1-share)

Storage of trade attempts

Allowed

One strategy (Ross Momentum)

One or two patterns

Strict risk limits

Not Allowed

Optimisation

Multiple strategies

Increased size

Exit Criteria

✔ Trades can execute safely
✔ Risk blocks work
✔ Trades are stored & reviewable

PHASE 5 — STRATEGY EXPANSION 📈
Purpose

Add new trading ideas safely.

This includes:

additional Ross patterns

scalping variants

quant-style strategies

Outputs

New strategy modules

New pattern detectors

Expanded analytics

Allowed

Feature growth

Strategy experimentation

Not Allowed

Architecture changes without review

Exit Criteria

✔ New strategies plug in cleanly
✔ No regression in safety

PHASE 6 — OPTIMISATION & SCALING 🚀
Purpose

Improve performance, speed, and scale after trust is established.

Outputs

Faster loops

Improved data handling

Better analytics

Increased position sizing (carefully)

Allowed

Performance work

Parallelism

Advanced tooling

Not Allowed

Breaking contracts

Sacrificing observability

Exit Criteria

✔ Performance improved without loss of clarity
✔ System remains explainable

PHASE TRANSITION RULE (CRITICAL)

You may only move to the next phase when:

Exit criteria are met

The transition is explicitly acknowledged

New phase is declared active

No silent transitions.

CURRENT STATUS (AUTHORITATIVE)

Active Phase: PHASE 1 — System Blueprint

Current Step: Step 2 of Phase 1

Next File: 02_SYSTEM_FLOW_CANONICAL.md

NEXT ACTION

When ready, say:

“Create 02_SYSTEM_FLOW_CANONICAL.md”

We will continue building the blueprint — calmly, clearly, and in control.