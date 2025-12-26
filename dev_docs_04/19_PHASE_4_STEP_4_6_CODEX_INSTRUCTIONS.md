PHASE 4 — STEP 4.6
Pattern Engine: Deterministic Teaching Patterns (Non-Empty Output)
Local Objective (STEP 4.6)

Upgrade the PatternEngine so it produces deterministic, teaching-only pattern detections from the scanner candidates.

This step answers:

“Given these momentum stocks, what kind of setup might this be?”

Still:

❌ no indicators

❌ no price series

❌ no real detection logic

❌ no trading

Just shape + explanation.

Allowed Files (ONLY THESE)
src/patterns/pattern_engine.py
src/models/data_models.py

Canonical Codex Instruction

(copy everything below exactly into Codex)

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system that is safe by default.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.6):
Upgrade the PatternEngine so it produces deterministic, teaching-only
pattern detections based on scanner candidates.

ALLOWED FILES TO MODIFY:
- src/models/data_models.py
- src/patterns/pattern_engine.py

REQUIREMENTS — data_models.py:
1. Add a dataclass named PatternResult with fields:
   - symbol: str
   - pattern_name: str
   - confidence: float
   - rationale: str
2. Teaching-first comments explaining each field.
3. No logic inside the dataclass.

REQUIREMENTS — pattern_engine.py:
1. PatternEngine.evaluate_patterns() must accept a list of ScannerCandidate.
2. For each candidate, produce zero or one PatternResult deterministically.
3. Use simple, transparent rules, for example:
   - High gap + low float → "Gap and Go (Teaching)"
   - Moderate gap + high float → "Momentum Continuation (Teaching)"
4. Print teaching logs explaining:
   - why a pattern was assigned
   - why a symbol may produce no pattern
5. Return a list of PatternResult.
6. Do NOT use randomness.
7. Do NOT import external libraries.
8. Do NOT implement real pattern logic.

FORBIDDEN:
- No indicators
- No historical candles
- No IBKR
- No APIs
- No randomness
- No complex scoring

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Change

You should now see logs like:

[PATTERN] Evaluating candidate ABC
[PATTERN] Assigned pattern: Gap and Go (Teaching) | confidence=0.65
[PATTERN] Evaluating candidate QRS
[PATTERN] No clear momentum pattern — teaching skip


And downstream modules will receive non-empty pattern outputs.

Definition of Done — STEP 4.6

PatternEngine returns non-empty results

PatternResult objects are structured

Logs explain every decision

System continues looping safely

No external dependencies

PR → merge → pull → run succeeds

Your next move

As always:

Paste the instruction into Codex

Create PR → merge

Pull in PyCharm

Run and paste the output

You’re now building the thinking layer of the system — exactly the right order.