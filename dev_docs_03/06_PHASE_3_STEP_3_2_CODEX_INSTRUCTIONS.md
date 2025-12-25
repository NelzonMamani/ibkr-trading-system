PHASE 3 — STEP 3.2 Codex Instructions (Core Orchestrator Skeleton)
Purpose

This document defines the exact Codex instructions for STEP 3.2.

STEP 3.2 introduces the Core Orchestrator, but still no real logic.
The orchestrator will exist only to:

explain the system flow

run a single deterministic cycle

print teaching-style logs

This step is about structure and sequencing, not behaviour.

Phase Context

Phase: PHASE 3 — Skeleton System (Restarted)

Step: STEP 3.2 — Core Orchestrator Skeleton

Mode: Teaching-First

Risk Level: Zero (structure only)

Local Objective (STEP 3.2)

Create a Core Orchestrator that represents the conceptual system flow
without importing or depending on real modules.

The orchestrator will simulate the pipeline using prints only.

What This Step MUST Do

Introduce a CoreOrchestrator class

Run a single orchestration cycle

Print each conceptual stage in order:

Scanner

Pattern Engine

Strategy

Risk

Execution

Storage

Be callable from main.py

What This Step MUST NOT Do

No imports from real modules

No module instantiation

No data passing

No trading logic

No external APIs

No configuration logic

This step is pure narrative structure.

Allowed Files to Modify
src/core/orchestrator.py
src/main.py


No other files may be created or modified.

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system skeleton that explains system flow clearly.

PHASE:
PHASE 3 — Skeleton System (Teaching-First)

LOCAL OBJECTIVE (STEP 3.2):
Create a Core Orchestrator skeleton that runs a single conceptual system cycle
and prints each stage of the trading system pipeline in order.

ALLOWED FILES TO MODIFY:
- src/core/orchestrator.py
- src/main.py

REQUIREMENTS — core/orchestrator.py:
1. Include a clear file-level docstring explaining:
   - this is the Core Orchestrator
   - it belongs to Phase 3
   - it contains no real logic
2. Define a CoreOrchestrator class.
3. Implement a method (e.g. run_once or run_cycle) that:
   - prints each conceptual system stage in order:
     Scanner → Patterns → Strategy → Risk → Execution → Storage
4. Use teaching-style print statements.
5. Do NOT import any real modules.

REQUIREMENTS — main.py:
1. Import CoreOrchestrator.
2. Instantiate it.
3. Call the single-cycle run method.
4. Preserve existing teaching logs.
5. Still exit cleanly.

FORBIDDEN:
- Do NOT import scanner, patterns, strategy, risk, execution, or storage modules
- Do NOT include trading logic
- Do NOT simulate data
- Do NOT optimise or refactor

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Output (Conceptual)

After merge, pull, and run:

[BOOT] Starting the IBKR Trading System skeleton.
[PHASE] PHASE 3 — Skeleton System (Teaching-First).
[ORCHESTRATOR] Initialising Core Orchestrator.
[CYCLE] Starting single orchestration cycle.
[SCAN] Scanner stage (skeleton).
[PATTERN] Pattern detection stage (skeleton).
[STRATEGY] Strategy decision stage (skeleton).
[RISK] Risk evaluation stage (skeleton).
[EXECUTION] Execution stage (skeleton).
[STORAGE] Storage stage (skeleton).
[CYCLE] Orchestration cycle complete.
[SHUTDOWN] Exiting gracefully. Goodbye!


Exact wording may differ; structure must be clear.

Definition of Done (STEP 3.2)

STEP 3.2 is DONE when:

CoreOrchestrator exists

main.py calls it

One full conceptual cycle prints

No real modules are imported

Code merged via PR

Code runs locally without error

What Comes After

Once STEP 3.2 is complete:

We proceed to STEP 3.3 — Individual Module Skeletons

This is where real module files (scanner, risk, etc.) appear — still empty, still safe

End of file.

Your next action (only one):

Copy the Canonical Codex Instruction

Paste into Codex

Let Codex create the PR

Then come back and say:

“STEP 3.2 complete — PR created”

You are doing this exactly right.