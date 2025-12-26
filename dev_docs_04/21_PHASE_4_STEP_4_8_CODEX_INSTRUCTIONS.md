PHASE 4 — STEP 4.8
Risk Engine: From Trade Intents → Risk Decisions (Teaching-Only, Safety-First)
1. Context (Why This Step Matters)

You now have TradeIntent objects, which represent:

“I would like to go LONG on ABC because of X.”

Before anything happens, a real system must answer:

“Is this trade allowed — and under what limits?”

This is risk’s job.

This step introduces permission, not action.

2. Local Objective (STEP 4.8)

Upgrade the RiskEngine so it evaluates TradeIntent objects and returns structured RiskDecision objects using conservative, teaching-only rules.

Still:

❌ no broker

❌ no sizing beyond placeholders

❌ no live capital

❌ no execution

3. Allowed Files (ONLY THESE)
src/models/data_models.py
src/risk/risk_engine.py

4. What We Will Introduce
New Data Model

RiskDecision

This represents permission + constraints, not execution.

Fields (teaching-first):

symbol

allowed (bool)

max_position_size

risk_level (LOW / MEDIUM / HIGH)

rationale

5. Teaching-Only Risk Rules (Explicit)

These rules are deterministic and conservative:

If TradeIntent.direction == "LONG" → allowed = True

max_position_size → always 1 share

risk_level derived from confidence:

confidence ≥ 0.75 → LOW

0.50–0.74 → MEDIUM

< 0.50 → HIGH

NEVER block trades yet (visibility > restriction)

6. Canonical Codex Instruction

(copy everything below exactly into Codex)

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a teaching-first, safe-by-default trading system.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE (STEP 4.8):
Upgrade the RiskEngine so it converts TradeIntent objects
into RiskDecision objects using deterministic, conservative,
teaching-only rules.

ALLOWED FILES TO MODIFY:
- src/models/data_models.py
- src/risk/risk_engine.py

REQUIREMENTS — data_models.py:
1. Add a dataclass named RiskDecision with fields:
   - symbol: str
   - allowed: bool
   - max_position_size: int
   - risk_level: str
   - rationale: str
2. Add teaching comments explaining:
   - RiskDecision is NOT an order
   - It represents permission and limits only

REQUIREMENTS — risk_engine.py:
1. RiskEngine.evaluate_trade_intent() must accept a TradeIntent.
2. For each TradeIntent:
   - Always return a RiskDecision.
3. Teaching-only deterministic rules:
   - direction == "LONG" → allowed = True
   - max_position_size = 1
   - risk_level:
       confidence >= 0.75 → "LOW"
       0.50–0.74 → "MEDIUM"
       < 0.50 → "HIGH"
4. Print teaching logs explaining:
   - why the trade is allowed
   - why the risk level was assigned
   - why max size is capped at 1
5. Do NOT block trades yet.

FORBIDDEN:
- No portfolio math
- No stops
- No percentages
- No IBKR
- No randomness
- No execution logic

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

7. Expected Runtime Change

You should now see logs like:

[RISK] Evaluating TradeIntent for ABC (LONG)
[RISK] Allowed = True (teaching visibility phase)
[RISK] Max position size capped at 1 share
[RISK] Risk level set to LOW based on confidence 0.82


And your TradeRecord will now include:

scanner_output ✅

pattern_output ✅

strategy_output ✅

risk_output ✅

execution_output ☐

8. Definition of Done — STEP 4.8

RiskDecision objects are created

Every TradeIntent is evaluated

Position size is capped

No execution occurs

System remains SIM-safe

PR → merge → pull → run succeeds

9. What Comes Next (Preview)

STEP 4.9 — Execution (SIM-Only, No Broker)
We will pretend to place orders and log them — still zero capital.

Proceed with STEP 4.8 when ready.
You are building this exactly like a professional trading system should be built.