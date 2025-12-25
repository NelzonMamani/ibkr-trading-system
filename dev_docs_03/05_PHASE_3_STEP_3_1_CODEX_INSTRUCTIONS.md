PHASE 3 — STEP 3.1 Codex Instructions (Project Skeleton & Entry Point)
Purpose

This document contains the exact, copy-paste-ready instruction block to send to Codex for STEP 3.1.

STEP 3.1 is intentionally small and conservative.
Its only goal is to establish a clean, runnable project entry point with no inter-module logic.

This step creates the foundation for all later wiring.

Phase Context

Phase: PHASE 3 — Skeleton System (Restarted)

Step: STEP 3.1 — Project Skeleton & Entry Point

Mode: Teaching-First

Risk Tolerance: Zero (no logic, no APIs)

Local Objective (STEP 3.1)

Create a minimal but correct project entry point that can be executed with
python src/main.py and clearly teaches what the system is doing at runtime.

What This Step MUST Do

Provide a main.py file

Print:

system boot

phase information

shutdown

Exit cleanly

Contain no orchestration

Contain no imports from other modules

What This Step MUST NOT Do

No imports from:

scanner

patterns

strategy

risk

execution

storage

No business logic

No trading logic

No external libraries

No configuration loaders

No environment detection

Allowed Files to Modify
src/main.py


No other files may be created or modified in this step.

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system skeleton that is safe, readable, and runnable.

PHASE:
PHASE 3 — Skeleton System (Teaching-First)

LOCAL OBJECTIVE (STEP 3.1):
Create a minimal project entry point that can be executed with
`python src/main.py` and prints clear teaching-style logs.

ALLOWED FILES TO MODIFY:
- src/main.py

FORBIDDEN:
- Do NOT import any other project modules
- Do NOT include trading logic
- Do NOT include configuration logic
- Do NOT connect to brokers or data sources
- Do NOT optimise or refactor

REQUIREMENTS FOR src/main.py:
1. Include a clear file-level docstring explaining:
   - what this file is
   - which phase it belongs to
   - what it intentionally does NOT do
2. Print teaching-style logs:
   - system boot
   - current phase
   - intention of the run
   - clean shutdown
3. Use a standard Python entry guard:
   if __name__ == "__main__":
4. The script must exit cleanly with no errors.

OUTPUT FORMAT:
- Output the FULL CONTENTS of src/main.py
- DO NOT output git diff format
- DO NOT include + / - lines
- DO NOT include explanations outside the file

STOP CONDITION:
If any requirement is unclear, ask a question before generating code.

Expected Result (After Merge & Pull)

When the user runs:

python src/main.py


They should see output similar to:

[BOOT] Trading System starting
[INFO] Phase: PHASE 3 — Skeleton System
[INFO] Purpose: establish clean entry point only
[INFO] No modules wired in this step
[SHUTDOWN] System exiting cleanly


Exact wording may vary, but intent must be clear.

Definition of Done (STEP 3.1)

STEP 3.1 is considered DONE when:

src/main.py exists

It runs without error

It prints clear teaching logs

No other files were touched

Code entered via GitHub PR

Code pulled and run locally in PyCharm

What Happens Next

After STEP 3.1 is complete and verified:

We proceed to STEP 3.2 — Core Orchestrator Skeleton

A new instruction file will be created:

06_PHASE_3_STEP_3_2_CODEX_INSTRUCTIONS.md


End of file.

When you are ready, your next action is:

Copy the Canonical Codex Instruction above

Paste it into Codex

Let Codex create the Pull Request

After that, come back and say:

“Codex finished STEP 3.1 — PR created”

We will then review it together, calmly and methodically.