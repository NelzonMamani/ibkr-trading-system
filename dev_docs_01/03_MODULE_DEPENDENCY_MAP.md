🧩 03_MODULE_DEPENDENCY_MAP.md

Authoritative Module Dependency Map — One-Way, Non-Circular Architecture

PURPOSE OF THIS DOCUMENT

This document defines the only allowed dependency relationships between modules.

Its goals are to:

Prevent circular dependencies

Preserve separation of concerns

Enable standalone execution and recovery

Make AI-assisted development safe and predictable

If a module imports something not listed here, it is a violation.

CORE ARCHITECTURAL PRINCIPLE

Dependencies flow downward only, from coordination → interpretation → permission → action → memory.

No module may depend on a module to its right in the flow.

HIGH-LEVEL DEPENDENCY FLOW (CANONICAL)
Core Orchestrator
   ↓
Scanner
   ↓
Patterns / Strategy
   ↓
Risk
   ↓
Execution
   ↓
Storage


This direction is strict.

MODULE DEPENDENCY TABLE (AUTHORITATIVE)
1️⃣ Core Orchestrator

May depend on:

Scanner

Pattern Engine

Strategy Runner

Risk Engine

Execution Engine

Storage Engine

Shared utilities (logging, time, validation)

Must NOT depend on:

Broker-specific logic

Pattern internals

Strategy-specific rules

Storage schema details

Role Reminder:
Controls when things run — not how they work.

2️⃣ Market Scanner

May depend on:

Data providers (market data, news metadata)

Shared utilities (logging, time, validation)

Declarative configuration

Must NOT depend on:

Strategy logic

Pattern detection

Risk rules

Execution or broker APIs

Storage write logic

Role Reminder:
Observes and explains the market — does not trade.

3️⃣ Pattern Detection Engine

May depend on:

Scanner outputs (structured data only)

Indicator computation utilities

Shared utilities

Must NOT depend on:

Risk rules

Execution logic

Broker APIs

Storage persistence

Role Reminder:
Detects setups and explains them — does not decide size or act.

4️⃣ Strategy Runner

May depend on:

Pattern Detection outputs

Strategy configuration

Shared utilities

Must NOT depend on:

Broker APIs

Execution logic

Storage persistence

Scanner internals

Role Reminder:
Decides intent — not permission or execution.

5️⃣ Risk Engine

May depend on:

Strategy intent

Account state

Symbol context

System health (from Orchestrator)

Shared utilities

Must NOT depend on:

Pattern internals

Strategy heuristics

Broker APIs (direct calls)

Storage internals

Role Reminder:
Protects capital — final gatekeeper.

6️⃣ Execution Engine

May depend on:

Risk-approved intent

Broker connector interfaces

Shared utilities

Must NOT depend on:

Scanner

Patterns

Strategy logic

Risk calculations

Storage internals

Role Reminder:
Executes orders — no thinking, no permission logic.

7️⃣ Storage Engine

May depend on:

Structured outputs from all upstream modules

Database connectors

Shared utilities

Must NOT depend on:

Scanner logic

Strategy logic

Risk decisions

Execution behaviour

Role Reminder:
Remembers everything — never influences decisions.

SHARED UTILITIES (SPECIAL CASE)
Examples

logging

time/session helpers

validation

configuration loaders

Rules

May be used by all modules

Must be stateless

Must not import business logic modules

FORBIDDEN DEPENDENCIES (NON-NEGOTIABLE)

❌ Scanner → Strategy
❌ Strategy → Risk internals
❌ Risk → Execution internals
❌ Execution → Strategy
❌ Storage → Any decision logic
❌ Any module → Core Orchestrator

Core Orchestrator is the top, never a dependency.

STANDALONE EXECUTION REQUIREMENT

Every module must be able to:

Run independently

Accept injected inputs

Produce prints + returns

Fail loudly and visibly

Dependency violations usually break this rule.

WHY THIS MATTERS (TEACHING NOTE)

Trading systems fail when execution logic leaks upward.

Software systems rot when dependencies become circular.

AI assistants hallucinate when boundaries are unclear.

This map keeps:

trading safe

code maintainable

AI controllable

STATUS

Phase: PHASE 1 — System Blueprint

Document Role: Architectural Guardrail

Next Step: Create 04_CODEX_OPERATING_MODEL.md

NEXT ACTION

When ready, say:

“Create 04_CODEX_OPERATING_MODEL.md”

This will define exactly how Codex is allowed to work with this project.