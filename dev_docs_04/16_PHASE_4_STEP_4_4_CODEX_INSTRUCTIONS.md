PHASE 4 — STEP 4.4
Behaviour Gating (Session + Mode Guards, Still No Trading)
Purpose

Introduce hard guards so the system can decide not to act based on:

RUN_MODE

Market session

Still:

❌ no IBKR

❌ no market data

❌ no execution logic

This step adds control, not capability.

Local Objective (STEP 4.4)

Gate the orchestrator cycle so it only runs when:

RUN_MODE != LIVE or

Market session is active (PRE / REGULAR / AFTER)

When gated:

explain why

idle safely

do not call the orchestrator cycle

Allowed Files
src/main.py


(Only. We keep this change isolated.)

Canonical Codex Instruction (copy exactly)
ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that cannot act
outside safe conditions.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.4):
Introduce behaviour gating based on RUN_MODE and market session,
without adding any trading logic.

ALLOWED FILES:
- src/main.py

REQUIREMENTS:
1. Before calling the orchestrator cycle, check:
   - RUN_MODE
   - current market session
2. If RUN_MODE == "LIVE" AND session == "CLOSED":
   - Do NOT call orchestrator.run_once()
   - Print clear teaching logs explaining why
3. If RUN_MODE != "LIVE":
   - Allow cycle to proceed (SIM/PAPER are always safe)
4. If session is active (PRE/REGULAR/AFTER):
   - Allow cycle to proceed
5. When gated, still sleep and continue looping.
6. Do NOT modify orchestrator or any modules.

FORBIDDEN:
- No IBKR
- No market data
- No execution
- No async/threading
- No refactors outside main.py

OUTPUT FORMAT:
- FULL FILE CONTENTS ONLY
- NO diff format
- NO + / - lines
- NO explanations outside code

Expected Behaviour (Example)

When market is closed and RUN_MODE = LIVE:

[SESSION] Market CLOSED.
[GATE] RUN_MODE=LIVE and market CLOSED — skipping orchestrator cycle.


When RUN_MODE = SIM (your current case):

[SESSION] Market CLOSED.
[GATE] RUN_MODE=SIM — cycle allowed (safe mode).

Definition of Done — STEP 4.4

Orchestrator cycle is conditionally gated

Logs explain why a cycle runs or doesn’t

Loop and shutdown remain intact

Delivered via PR → merge → pull → run

Your next move

Proceed exactly as before:

Paste the instruction into Codex

Create PR → merge

Pull in PyCharm

Run and paste output

You’re now adding safety interlocks—this is the last step before any real data or brokers ever appear.