📘 dev_docs_01 / README.md

System Blueprint — Phase 1

PROJECT NAME

IBKR Trading System — Ross Cameron Momentum First

CURRENT STATUS

Current Phase: PHASE 1 — System Blueprint

Phase Status: IN PROGRESS

Previous Phase: PHASE 0 — Intent Capture (COMPLETED & FROZEN)

Next Phase: PHASE 2 — Interface & Contracts (NOT STARTED)

PURPOSE OF THIS FOLDER (dev_docs_01)

This folder contains the System Blueprint.

Its purpose is to create a single, unambiguous understanding of the trading system before any code is written or modified.

This is the bridge between:

Intent & thinking (captured in dev_docs_00)

Execution & coding (future phases)

Nothing in this folder is code.
Everything in this folder is decision-making, structure, and clarity.

WHAT PHASE 1 IS ABOUT

PHASE 1 exists to answer, clearly and permanently:

What system are we building?

How does it work end-to-end?

What modules exist and why?

In what order will development proceed?

How will we safely use AI (Codex)?

If something is unclear later, this folder is the source of truth.

WHAT IS ALLOWED IN PHASE 1

✅ Writing and refining documentation
✅ Clarifying system flow and responsibilities
✅ Defining development phases and checkpoints
✅ Deciding what comes first and what comes later
✅ Referencing (but not editing) dev_docs_00

WHAT IS NOT ALLOWED IN PHASE 1

❌ Writing Python code
❌ Creating skeleton files
❌ Implementing scanners, strategies, or connectors
❌ Asking Codex to generate code
❌ Optimisation or performance discussions
❌ “We’ll figure it out later” decisions

If something belongs to a later phase, it is explicitly deferred.

RELATIONSHIP TO OTHER DOCUMENT FOLDERS
dev_docs_00/ — Frozen Intent (READ-ONLY)

Contains:

Original vision

Strategy specs

Module requirements

Governance, doctrine, recovery protocols

These files must not be modified casually.
They represent what you were trying to accomplish.

dev_docs_01/ — System Blueprint (THIS FOLDER)

Contains:

Clean, reconciled understanding

One authoritative system flow

One authoritative development roadmap

Clear rules for AI usage

This folder defines how we will proceed now.

Future folders (not yet active)

dev_docs_02/ → Codex task instructions

dev_docs_03/ → Implementation notes & decisions

src/ → Actual Python code (later phases only)

GLOBAL OBJECTIVE (RECONFIRMED)

Build a Python-based, live-capable trading system that:

Automates Ross Cameron’s Momentum strategy first

Is strategy-agnostic by design

Trades via Interactive Brokers (IBKR / TWS)

Starts with minimal live risk (1-share testing)

Is teaching-first (comments, logs, explainability)

Persists full trade context for learning and review

Can be recovered and reconstructed safely

HOW TO USE THIS FILE

Open this file when:

You feel lost

You return after a break

You’re unsure what to do next

You’re tempted to jump ahead

If your action contradicts what’s written here, stop.

NEXT STEPS IN PHASE 1

The documents to be created in this folder, in order:

01_DEVELOPMENT_ROADMAP.md
→ All phases, steps, and transitions

02_SYSTEM_FLOW_CANONICAL.md
→ One definitive end-to-end system flow

03_MODULE_DEPENDENCY_MAP.md
→ Clear, one-directional module dependencies

04_CODEX_OPERATING_MODEL.md
→ How AI (Codex) is allowed to work

05_DEFINITION_OF_DONE.md
→ When Phase 1 is officially complete

FINAL NOTE

PHASE 1 is about calm clarity, not speed.

Once this blueprint is complete:

Coding becomes mechanical

AI becomes safe to use

Progress becomes predictable

Do not rush this phase.
This is where confidence is built.

STATUS

PHASE 1 — ACTIVE
STEP 1 — COMPLETE (README CREATED)
NEXT STEP — Create 01_DEVELOPMENT_ROADMAP.md

✅ What to do next

When ready, say:

“Create 01_DEVELOPMENT_ROADMAP.md”

We will continue one step at a time, with full awareness of where you are in the process.