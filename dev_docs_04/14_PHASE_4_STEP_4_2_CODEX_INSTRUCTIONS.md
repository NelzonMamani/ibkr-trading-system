PHASE 4 — STEP 4.2 Codex Instructions (Continuous Run Loop & Graceful Shutdown)
Purpose

STEP 4.2 replaces the single-run execution with a controlled continuous run loop.

This is the moment the system starts to behave like a real service:

it stays alive

it loops

it can be stopped safely

Still:

❌ no trading

❌ no data feeds

❌ no execution risk

Phase Context

Phase: PHASE 4 — Minimal Live-Capable System

Step: STEP 4.2 — Continuous Run Loop & Graceful Shutdown

Safety Level: Very High

Local Objective (STEP 4.2)

Modify the system so it runs continuously in a controlled loop,
sleeps between cycles, and shuts down cleanly when interrupted.

What This Step MUST Do

Replace “run once” behaviour with a loop:

e.g. while True

Add a sleep interval between cycles (e.g. 2–5 seconds)

Handle KeyboardInterrupt (Ctrl+C) gracefully

Print teaching-style logs for:

loop start

each cycle

sleep

shutdown

What This Step MUST NOT Do

No new logic in scanner, patterns, etc.

No data fetching

No IBKR

No threading

No async

No performance tuning

This is control flow only.

Allowed Files to Modify
src/main.py


(We intentionally keep this change isolated.)

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that runs safely and predictably.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.2):
Replace single-run execution with a controlled continuous run loop
that can be stopped safely with Ctrl+C.

ALLOWED FILES TO MODIFY:
- src/main.py

REQUIREMENTS — main.py:
1. Keep existing boot, phase, mode, and intent logs.
2. Replace single orchestrator run with a loop, e.g. while True.
3. Call the orchestrator cycle once per loop iteration.
4. Add a sleep between cycles (e.g. 3 seconds).
5. Handle KeyboardInterrupt:
   - Print a clear shutdown message
   - Exit the loop cleanly
6. Add teaching-style logs for:
   - loop start
   - each cycle
   - sleeping
   - shutdown

FORBIDDEN:
- Do NOT modify orchestrator or modules
- Do NOT add data logic
- Do NOT add threading or async
- Do NOT optimise timing

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Behaviour

When you run:

python src/main.py


You should see:

the system looping every few seconds

repeated orchestrator cycles

clean logs

Ctrl+C stops it gracefully

Definition of Done (STEP 4.2)

STEP 4.2 is complete when:

System runs continuously

Ctrl+C stops it cleanly

No errors occur

No new behaviour added beyond looping

Delivered via PR → merge → pull

Your next action (as usual)

Copy the Canonical Codex Instruction

Paste into Codex

Let Codex create the PR

Merge → pull → run

Paste your runtime output

You are now entering the phase where the system feels alive — and you’re doing it the safe way.