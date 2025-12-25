PHASE 3 — STEP 3.4 Codex Instructions (Wire Orchestrator to Module Skeletons)
Purpose

STEP 3.4 is where the system becomes real as a system.

In this step:

the Core Orchestrator will instantiate real module skeletons

the orchestrator will call their placeholder methods

data will flow conceptually from one stage to the next

Still:

❌ no trading logic

❌ no calculations

❌ no external APIs

This step teaches how modular systems communicate.

Phase Context

Phase: PHASE 3 — Skeleton System (Restarted)

Step: STEP 3.4 — Wire Orchestrator to Module Skeletons

Mode: Teaching-First

Risk Level: Low (structure + calls only)

Local Objective (STEP 3.4)

Update the Core Orchestrator so it imports, instantiates, and calls each module skeleton in sequence, passing placeholder data between stages.

System Flow to Implement (Conceptual Only)

The orchestrator must follow this order:

Scanner

Pattern Engine

Strategy Runner

Risk Engine

Execution Engine

Storage Engine

Each stage:

prints when called

returns placeholder data

passes that data to the next stage

Allowed Files to Modify
src/core/orchestrator.py
src/main.py


No module files should be modified in this step.

What This Step MUST Do
In core/orchestrator.py

Import the module skeleton classes:

Scanner

PatternEngine

StrategyRunner

RiskEngine

ExecutionEngine

StorageEngine

Instantiate each module in __init__.

In the orchestration cycle:

call each module’s placeholder method

pass placeholder output forward

print teaching-style logs before and after each call

Handle empty or None returns gracefully.

In main.py

No structural changes.

Continue to:

instantiate CoreOrchestrator

run one cycle

shut down cleanly

What This Step MUST NOT Do

No business logic

No conditionals beyond None / empty checks

No data models

No try/except complexity

No logging frameworks

No config loading

No external APIs

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system skeleton that demonstrates modular system flow.

PHASE:
PHASE 3 — Skeleton System (Teaching-First)

LOCAL OBJECTIVE (STEP 3.4):
Wire the Core Orchestrator to the individual module skeletons so that
a single orchestration cycle calls each module in sequence using placeholder data.

ALLOWED FILES TO MODIFY:
- src/core/orchestrator.py
- src/main.py

REQUIREMENTS — core/orchestrator.py:
1. Import the following classes:
   - Scanner
   - PatternEngine
   - StrategyRunner
   - RiskEngine
   - ExecutionEngine
   - StorageEngine
2. Instantiate each class in the CoreOrchestrator __init__ method.
3. In the orchestration cycle method:
   - call the scanner method and store its return value
   - pass that value to the pattern engine method
   - pass pattern results to strategy runner
   - pass strategy output to risk engine
   - pass risk output to execution engine
   - pass execution output to storage engine
4. Add teaching-style print statements before and after each stage.
5. Handle None or empty returns gracefully.
6. Do NOT add real logic or calculations.

REQUIREMENTS — main.py:
1. No behavioural changes.
2. Continue to run one orchestrator cycle and exit cleanly.

FORBIDDEN:
- Do NOT modify module skeleton files
- Do NOT add trading logic
- Do NOT add external dependencies
- Do NOT optimise or refactor

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Output (Conceptual)

After merge, pull, and run:

[BOOT] Starting the IBKR Trading System skeleton.
[PHASE] PHASE 3 — Skeleton System (Teaching-First).
[INFO] Core Orchestrator initialised.
[CYCLE] Starting orchestrator cycle.
[SCAN] Calling Scanner.run_scan()
[SCAN] Scanner returned empty candidate list.
[PATTERN] Calling PatternEngine.detect_patterns()
[PATTERN] No patterns detected (placeholder).
[STRATEGY] Calling StrategyRunner.decide_strategy()
[STRATEGY] No trade intent generated (placeholder).
[RISK] Calling RiskEngine.evaluate_risk()
[RISK] Trade blocked or no intent (placeholder).
[EXECUTION] Calling ExecutionEngine.execute_trade()
[EXECUTION] No execution performed (placeholder).
[STORAGE] Calling StorageEngine.store_record()
[STORAGE] Record accepted (placeholder).
[CYCLE] Orchestrator cycle complete.
[SHUTDOWN] Exiting gracefully. Goodbye!


Exact wording may differ; sequence and intent must be clear.

Definition of Done (STEP 3.4)

STEP 3.4 is DONE when:

Orchestrator imports all module skeletons

All module methods are called in order

Placeholder data flows between stages

No runtime errors occur

Code merged via PR

System runs cleanly in PyCharm

What Comes Next

After STEP 3.4:

STEP 3.5 — Skeleton Trade Record & Storage Flow

This introduces a minimal data model (still no logic)

Your next action

Copy the Canonical Codex Instruction above

Paste it into Codex

Let Codex create the Pull Request

Then come back and say:

“STEP 3.4 complete — PR created”

You are now building the system exactly the way senior engineers do — methodically, visibly, and safely.