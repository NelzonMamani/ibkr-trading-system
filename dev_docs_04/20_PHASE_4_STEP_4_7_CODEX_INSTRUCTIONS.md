PHASE 4 — STEP 4.7
Strategy Runner: From Patterns → Trade Intents (Teaching-Only)
1. Context (Where We Are)

Current pipeline state (✔ = working):

✔ Scanner → static, realistic candidates

✔ Pattern Engine → deterministic teaching patterns

❌ Strategy Runner → still empty

❌ Risk → placeholder

❌ Execution → placeholder

❌ Storage → placeholder

This step activates the brain, but not the hands.

2. Local Objective (STEP 4.7)

Upgrade the StrategyRunner so it converts PatternResult objects into TradeIntent objects in a deterministic, teaching-only way.

This answers the question:

“Given these patterns, would I want to trade this — and why?”

Still:

❌ no broker

❌ no orders

❌ no sizing

❌ no real edge claims

Just decision framing.

3. Allowed Files (ONLY THESE)
src/models/data_models.py
src/strategy/strategy_runner.py

4. What We Will Introduce
New Data Model

TradeIntent

This is NOT an order.
It is a thought.

Fields (teaching-first):

symbol

direction (LONG / SHORT / NONE)

strategy_name

confidence

rationale

5. Canonical Codex Instruction

(copy everything below exactly into Codex)

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a teaching-first, safe-by-default trading system.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.7):
Upgrade the StrategyRunner so it converts PatternResult objects
into TradeIntent objects using deterministic, teaching-only rules.

ALLOWED FILES TO MODIFY:
- src/models/data_models.py
- src/strategy/strategy_runner.py

REQUIREMENTS — data_models.py:
1. Add a dataclass named TradeIntent with fields:
   - symbol: str
   - direction: str  # "LONG", "SHORT", or "NONE"
   - strategy_name: str
   - confidence: float
   - rationale: str
2. Add teaching comments explaining that a TradeIntent is NOT an order.
3. No logic inside the dataclass.

REQUIREMENTS — strategy_runner.py:
1. StrategyRunner.generate_trade_intent() must accept a list of PatternResult.
2. For each PatternResult:
   - Generate ONE TradeIntent.
3. Deterministic teaching rules only, for example:
   - "Gap and Go (Teaching)" → LONG
   - "Momentum Continuation (Teaching)" → LONG
4. Print teaching logs explaining:
   - why a trade intent was created
   - why confidence is assigned
5. Return a list of TradeIntent.
6. Do NOT filter aggressively — this is for teaching visibility.
7. Do NOT use randomness.
8. Do NOT implement real strategy logic.

FORBIDDEN:
- No price levels
- No indicators
- No IBKR
- No execution logic
- No randomness

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

6. Expected Runtime Change

You should now see logs like:

[STRATEGY] Evaluating pattern Gap and Go (Teaching) for ABC
[STRATEGY] Created LONG trade intent — momentum continuation framing


And your TradeRecord will now contain:

scanner_output ✅

pattern_output ✅

strategy_output ✅

Risk will finally have something real to evaluate next.

7. Definition of Done — STEP 4.7

StrategyRunner produces non-empty trade intents

TradeIntent objects are structured and logged

No execution occurs

System remains SIM-safe

PR → merge → pull → run succeeds

8. Your Exact Workflow (Reminder)

Paste the instruction into Codex

Let Codex generate code

Click Create PR

Merge on GitHub

Pull in PyCharm

Run main.py

Paste output here

When you’re ready, execute STEP 4.7.
After that, we move to Risk — where discipline enters the system.