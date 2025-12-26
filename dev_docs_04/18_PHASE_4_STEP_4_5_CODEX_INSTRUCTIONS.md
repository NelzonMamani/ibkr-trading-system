PHASE 4 — STEP 4.5
Simulated Market Data → Scanner Produces Non-Empty Output (Teaching-First)
Phase Context

Phase: PHASE 4 — Minimal Live-Capable System

Step: STEP 4.5 — Simulated Market Data Injection

Risk Level: Zero (no broker, no real data)

Global Objective (Reminder)

Build a professional, teaching-first trading system that can be exercised end-to-end without touching real markets.

Local Objective (STEP 4.5)

Upgrade the Scanner so it returns a deterministic, hard-coded list of fake momentum candidates, allowing downstream modules (Patterns → Strategy → Risk → Execution → Storage) to receive real-looking inputs.

This is the first step where:

the system no longer passes empty lists

logs become more interesting

flow becomes realistic

What This Step MUST Do
1. Introduce a scanner output model

Create a simple dataclass representing a scanned stock.

2. Make the scanner return candidates

Always return 3–5 fake symbols

Deterministic (same output every run)

No randomness

3. Teach while printing

Logs must clearly say:

this is simulated data

why each symbol would be interesting (gap, RVOL, float)

What This Step MUST NOT Do

❌ No real market data
❌ No APIs
❌ No IBKR
❌ No randomness
❌ No scoring logic
❌ No time dependence

This is shape + flow only.

Allowed Files to Modify (ONLY THESE)
src/models/data_models.py
src/scanner/scanner.py


No other files may be touched.

Canonical Codex Instruction
(Copy everything below EXACTLY into Codex)
ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that is safe by default.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.5):
Upgrade the scanner from returning an empty list to returning a deterministic,
hard-coded list of fake momentum candidates so downstream modules can be exercised.

ALLOWED FILES TO MODIFY:
- src/models/data_models.py
- src/scanner/scanner.py

REQUIREMENTS — data_models.py:
1. Add a dataclass named ScannerCandidate.
2. Fields:
   - symbol: str
   - price: float
   - gap_percent: float
   - rvol: float
   - float_millions: float
   - rationale: str
3. Teaching-first comments explaining each field.
4. No logic inside the dataclass.

REQUIREMENTS — scanner.py:
1. Scanner.run_scan_cycle() must return List[ScannerCandidate].
2. Return a deterministic, hard-coded list of 3–5 candidates.
3. Example symbols may be fake (e.g., "ABC", "XYZ", "MOMO").
4. Print teaching logs explaining:
   - that these are simulated candidates
   - why each candidate looks interesting (gap, RVOL, float)
5. Do NOT use randomness.
6. Do NOT fetch real data.
7. Do NOT import external libraries.

FORBIDDEN:
- No IBKR
- No Yahoo / web
- No APIs
- No randomness
- No complex scoring logic

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Change (What you’ll see)

Instead of:

[SCAN] Scanner returned no candidates — placeholder outcome.


You should see:

[SCAN] Simulated scanner running (Phase 4.5).
[SCAN] Candidate: ABC | gap=12% | RVOL=6.2 | float=8.5M
[SCAN] Candidate: XYZ | gap=9% | RVOL=4.8 | float=12.1M
...


And downstream modules will now receive non-empty inputs.

Definition of Done — STEP 4.5

Scanner returns non-empty list every cycle

Output objects are structured (dataclass)

Logs clearly explain simulation

Orchestrator continues looping

No external dependencies

PR → merge → pull → run succeeds

Your next move (as usual)

Paste the instruction into Codex

Let Codex create the PR

Merge on GitHub

Pull into PyCharm

Run and paste the output

After STEP 4.5, the system will finally look alive — still 100% safe.