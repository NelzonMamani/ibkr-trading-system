PHASE 4 — STEP 4.4 Validation Tests (Prove the Gate Works)

Purpose
We will verify the gate blocks cycles only in the dangerous case:

RUN_MODE = LIVE and SESSION = CLOSED


Test 1 — Safe Mode (SIM) while CLOSED (what you already saw)
✅ Expected:


Cycle runs


Orchestrator runs


Logs show safe progression


Result: PASSED (your output)

Test 2 — LIVE Mode while CLOSED (must block orchestrator)
What you do (quick, manual)


Open:
src/config/system_config.py



Temporarily change:


RUN_MODE = "LIVE" (or whatever representation you used)




Run src/main.py


Expected output (key lines)
You should see something like:
[SESSION] Detected market session: CLOSED
[GATE] RUN_MODE=LIVE and market CLOSED — skipping orchestrator cycle.
[SLEEP] Sleeping for 3 seconds before next cycle.

And importantly:


You should NOT see:
[INFO] Starting orchestrator cycle (teaching-only).



After test
Change RUN_MODE back to SIM.

Test 3 — LIVE Mode during ACTIVE session (PRE/REGULAR/AFTER)
We will do this later when we add a manual override (so you don’t need to wait for market hours).
Not needed yet.

✅ Now Continue Phase 4
Next step is where the system becomes “more real” without IBKR:
STEP 4.5 — Simulated Market Data Injection (Deterministic Fake Data)
This is the step where:


scanner stops returning empty lists


pattern engine receives something


you can start seeing symbol candidates in logs


Still:


❌ no broker


❌ no real-time feeds


❌ no trading



Next file (filename first)
18_PHASE_4_STEP_4_5_CODEX_INSTRUCTIONS.md

PHASE 4 — STEP 4.5 Codex Instructions (Simulated Market Data → Scanner Non-Empty Output)

Local Objective (STEP 4.5)

Make the scanner return a deterministic list of 3–5 fake momentum candidates so downstream modules can be exercised with real-looking flow.


Allowed Files (only these)
src/scanner/scanner.py
src/models/data_models.py


Canonical Codex Instruction (copy exactly)
ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that is safe by default.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.5):
Upgrade the scanner from returning an empty list to returning a deterministic,
hard-coded list of 3–5 fake momentum candidates, so downstream modules can be exercised.

ALLOWED FILES TO MODIFY:
- src/scanner/scanner.py
- src/models/data_models.py

REQUIREMENTS — data_models.py:
1. Add a simple dataclass named ScannerCandidate with fields:
   - symbol: str
   - price: float
   - gap_percent: float
   - rvol: float
   - float_millions: float
   - rationale: str
2. Keep it Phase-4 teaching-first.
3. No logic, no validation.

REQUIREMENTS — scanner.py:
1. Ensure Scanner.run_scan_cycle() returns List[ScannerCandidate].
2. Return a deterministic hard-coded list of 3–5 candidates, for example:
   - "ABC", "XYZ", etc.
3. Print teaching logs explaining:
   - these are fake/simulated candidates
   - why each candidate would be interesting (gap/rvol/float)
4. Do NOT use randomness.
5. Do NOT fetch real data.
6. Do NOT import external dependencies.

FORBIDDEN:
- No IBKR
- No web/yahoo
- No API calls
- No randomness
- No complex scoring

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.


Definition of Done (STEP 4.5)


Scanner returns non-empty list every cycle


Candidates are structured objects, not raw dicts


Logs explain each candidate


Orchestrator continues working


No external dependencies


PR → merge → pull → run success



Your next move (two options)
Option A (recommended)
Run Test 2 (LIVE+CLOSED gate proof) quickly, then continue to Step 4.5.
Option B
Skip the test for now and go straight to Step 4.5.
Either way is acceptable.
If you want the cleanest learning path, do this next:

“Proceed — Step 4.5 (scanner simulated candidates)”

