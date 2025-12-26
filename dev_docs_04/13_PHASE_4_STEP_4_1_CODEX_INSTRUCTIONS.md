PHASE 4 — STEP 4.1 Codex Instructions (Runtime Configuration & Run Modes)
Purpose

STEP 4.1 introduces explicit runtime configuration and run modes so the system always knows:

how “dangerous” it is allowed to be

whether external side-effects are permitted

This step is the foundation for safe trading development.

Phase Context

Phase: PHASE 4 — Minimal Live-Capable System

Step: STEP 4.1 — Runtime Configuration & Run Modes

Safety Principle: Default to safe mode (SIM)

Local Objective (STEP 4.1)

Add a minimal configuration module that defines RUN_MODE as one of:
SIM, PAPER, LIVE, defaulting to SIM, and print it at boot.

No behavioural changes beyond:

reading the mode

printing it

making it available to the orchestrator for future gating

What This Step MUST Do

Define a run mode enum or constant set:

SIM

PAPER

LIVE

Set default run mode to SIM

Print the run mode during system boot

Make run mode accessible to other modules (importable)

What This Step MUST NOT Do

No IBKR

No data logic

No trading logic

No environment variable parsing (yet)

No config files (yet)

No risk gating changes (yet)

This step is “mode exists and is visible”, nothing else.

Allowed Files to Modify / Create

Allowed to create one new file:

src/config/runtime_config.py


Allowed to modify:

src/main.py


No other files may be created or changed.

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that is safe by design.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.1):
Introduce explicit runtime run modes (SIM / PAPER / LIVE), default to SIM,
and print the selected mode at system boot.

ALLOWED FILES TO CREATE:
- src/config/runtime_config.py

ALLOWED FILES TO MODIFY:
- src/main.py

REQUIREMENTS — runtime_config.py:
1. Include a file-level docstring that explains:
   - this file defines runtime safety mode
   - Phase 4 step 4.1 purpose
2. Define a RunMode representation:
   - either an Enum (preferred) or string constants
   - valid values: SIM, PAPER, LIVE
3. Define a single source of truth:
   - DEFAULT_RUN_MODE = SIM
4. Provide a small helper function, e.g. get_run_mode(), that returns the current run mode.
   - For now it should simply return DEFAULT_RUN_MODE
   - No env parsing yet

REQUIREMENTS — main.py:
1. Import get_run_mode() (or equivalent).
2. Print a teaching-style line showing the active run mode, e.g.:
   [MODE] RUN_MODE = SIM (safe default)
3. Preserve existing Phase 3/Phase 4 teaching logs and orchestrator invocation.
4. Do NOT change orchestrator behavior beyond printing mode.

FORBIDDEN:
- Do NOT add IBKR code
- Do NOT add data fetching
- Do NOT change orchestration flow
- Do NOT read environment variables yet
- Do NOT add new dependencies

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only for each file changed/created
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Output (Conceptual)

When you run:

python src/main.py


You should see something like:

[BOOT] Starting the IBKR Trading System skeleton.
[PHASE] PHASE 4 — Minimal Live-Capable System
[MODE] RUN_MODE = SIM (safe default)
...

Definition of Done (STEP 4.1)

STEP 4.1 is complete when:

src/config/runtime_config.py exists

RUN_MODE is defined and defaults to SIM

main.py prints the mode at startup

system still runs cleanly (exit code 0)

changes delivered through PR → merge → pull workflow

What Comes Next

After STEP 4.1:

STEP 4.2 introduces a controlled run loop + graceful shutdown

Next file will be:

14_PHASE_4_STEP_4_2_CODEX_INSTRUCTIONS.md


End of file.

Your next action

Copy the Canonical Codex Instruction above

Paste it into Codex

Let Codex create a Pull Request

Merge, pull, run

Then come back and paste your runtime output.