PHASE 4 — STEP 4.3
Configuration & Session Awareness (Teaching-First, No Behaviour Change)
Phase Context

Phase: PHASE 4 — Minimal Live-Capable System

Step: STEP 4.3 — Configuration & Session Awareness

Risk Level: Zero (no trading, no data, no broker)

Global Objective (Reminder)

Build a professional, teaching-first trading system that is:

safe by default

explicit in intent

impossible to “accidentally go live”

Local Objective (STEP 4.3)

Introduce a central configuration layer and market session awareness
without changing runtime behaviour.

This step is about clarity and control, not action.

What This Step MUST Do

Create a new configuration module:

src/config/system_config.py


Define explicit, human-readable configuration values, including:

RUN_MODE (SIM / PAPER / LIVE)

CYCLE_SLEEP_SECONDS

ACTIVE_SESSIONS (PRE / REGULAR / AFTER)

Introduce a simple session helper:

determines current session based on local time

returns "PRE", "REGULAR", "AFTER", or "CLOSED"

Add teaching-style prints explaining:

which session we are in

whether the system would be allowed to act

why the system continues idling in skeleton mode

What This Step MUST NOT Do

❌ No market hours enforcement
❌ No pausing or sleeping based on session
❌ No IBKR
❌ No data
❌ No logic changes to orchestrator flow

This is visibility only, not control yet.

Allowed Files to Modify
src/config/system_config.py   (NEW FILE)
src/main.py                   (IMPORT + PRINT ONLY)


No other files may be touched.

Teaching Constraint (Very Important)

Configuration must be:

explicit

named clearly

printed at startup

No “magic values”

No hidden defaults

A future trader (you) must be able to answer:

“Why is the system behaving like this right now?”

Just by reading logs + config.

Canonical Codex Instruction
(Copy everything below exactly into Codex)
ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that is safe by default.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.3):
Introduce a central configuration module and basic market session awareness
WITHOUT changing system behaviour.

ALLOWED FILES:
- src/config/system_config.py (new)
- src/main.py (import + teaching prints only)

REQUIREMENTS — system_config.py:
1. Define RUN_MODE with default "SIM".
2. Define CYCLE_SLEEP_SECONDS (use 3).
3. Define ACTIVE_SESSIONS = ["PRE", "REGULAR", "AFTER"].
4. Implement a helper function get_current_market_session():
   - returns "PRE", "REGULAR", "AFTER", or "CLOSED"
   - simple time-based logic is sufficient
5. Add clear teaching comments explaining each value.

REQUIREMENTS — main.py:
1. Import configuration values.
2. Print configuration at startup in human-readable form.
3. Print detected market session at runtime.
4. Print whether the system WOULD be allowed to trade
   (but do not change behaviour).
5. Do NOT modify orchestrator logic or loop structure.

FORBIDDEN:
- No execution logic
- No pausing based on session
- No broker interaction
- No threading or async
- No behavioural changes

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Output (Example)

You should see logs like:

[CONFIG] RUN_MODE = SIM
[CONFIG] Active sessions = PRE, REGULAR, AFTER
[SESSION] Current market session detected: PRE
[SESSION] Trading would be allowed in this session (conceptual only)


But nothing changes in execution.

Definition of Done — STEP 4.3

STEP 4.3 is complete when:

Config exists in one place

Session is detected and printed

Behaviour remains identical

System still loops and exits safely

Delivered via PR → merge → pull → run

Your next move

As usual:

Paste the instruction into Codex

Let Codex create the PR

Merge on GitHub

Pull in PyCharm

Run and paste the output

You are now building the safety rails that separate hobby bots from professional trading systems.