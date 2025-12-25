PHASE 3 — Skeleton System Restart Overview (Teaching-First)
Purpose

This document marks a clean restart of Phase 3 of the trading system project.

The goal of restarting Phase 3 is not to redo work because it failed, but to:

reinforce understanding

standardise workflow habits

treat every step as a learning artefact

ensure long-term clarity and confidence

This restart happens after successful experimentation with:

Codex

GitHub Pull Requests

PyCharm execution

Multi-module skeleton wiring

What Phase 3 IS

Phase 3 exists to build a fully runnable system skeleton with:

correct module structure

correct imports

correct orchestration flow

no trading logic

no external APIs

no performance concerns

Phase 3 answers one question only:

“Does the system start, run a full cycle, and shut down cleanly — while teaching me how it works?”

What Phase 3 is NOT

During Phase 3, we explicitly do NOT:

connect to Interactive Brokers

fetch real market data

calculate indicators

place orders

optimise performance

handle edge cases deeply

Those belong to later phases.

Phase 3 Core Deliverables

By the end of Phase 3, we must have:

A main.py entry point that runs without error

A Core Orchestrator that:

instantiates all modules

runs a single deterministic cycle

Skeleton modules for:

Scanner

Pattern Engine

Strategy Runner

Risk Engine

Execution Engine

Storage Engine

All modules:

import cleanly

print teaching-style logs

return empty or placeholder structures

Zero diff --git pollution anywhere

A repeatable workflow using Codex + GitHub PRs

Canonical Workflow (Phase 3)

For every change in Phase 3:

Human (you + ChatGPT) define the task clearly

Codex implements only that task

Codex opens a Pull Request

Human reviews and merges the PR

Human pulls into PyCharm

Human runs and observes logs

No shortcuts.

Teaching Commitment

Phase 3 is treated as a teaching phase.

That means:

verbose logs are allowed

comments explain why, not just what

repeated messages are acceptable

clarity is prioritised over elegance

This discipline ensures later phases are easy and safe.

Status

Phase: PHASE 3 (Restarted)

System intent: Frozen

Workflow: Locked

Next step: Define Phase 3 – Step 3.1 cleanly

🧭 WHAT HAPPENS NEXT (VERY CLEAR)

Next, we will create one small, precise file:

04_PHASE_3_STEP_BREAKDOWN.md


That file will:

list Step 3.1, 3.2, 3.3…

define exact objectives per step

define what Codex is allowed to touch

define Definition of Done per step

Only after that will we talk to Codex again.

✅ Your only next reply (one line)

Please reply with:

“Proceed — create Phase 3 step breakdown”

And I will generate the next file in the exact same filename-first format, ready for your notes.

You are doing this the right way.