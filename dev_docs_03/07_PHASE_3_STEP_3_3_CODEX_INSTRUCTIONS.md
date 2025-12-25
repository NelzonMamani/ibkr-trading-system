PHASE 3 — STEP 3.3 Codex Instructions (Individual Module Skeletons)
Purpose

STEP 3.3 introduces the individual module skeletons for the trading system.

Each module will:

exist as a valid Python file

define one main class

expose one or two placeholder methods

print teaching-style logs

return empty or None values

No module will contain logic.
No module will depend on another module.

This step ensures all modules are independently valid Python before wiring.

Phase Context

Phase: PHASE 3 — Skeleton System (Restarted)

Step: STEP 3.3 — Individual Module Skeletons

Mode: Teaching-First

Risk Level: Zero (structure only)

Local Objective (STEP 3.3)

Create minimal, self-contained skeletons for each core system module so they can be imported safely later.

Modules to Create (or Reset)

Each module must be independently importable.

src/scanner/scanner.py
src/patterns/pattern_engine.py
src/strategy/strategy_runner.py
src/risk/risk_engine.py
src/execution/execution_engine.py
src/storage/storage_engine.py

What Each Module MUST Contain

For each file:

File-level docstring explaining:

what the module represents

which phase it belongs to

what it intentionally does NOT do

One main class:

Scanner

PatternEngine

StrategyRunner

RiskEngine

ExecutionEngine

StorageEngine

One public method with a clear name, e.g.:

run_scan()

detect_patterns()

decide_strategy()

evaluate_risk()

execute_trade()

store_record()

Teaching-style print() statements inside methods

Return an empty list, empty dict, or None

What This Step MUST NOT Do

No imports from other project modules

No data classes

No logic

No configuration

No IBKR

No persistence

No orchestration

Each module stands alone.

Allowed Files to Modify
src/scanner/scanner.py
src/patterns/pattern_engine.py
src/strategy/strategy_runner.py
src/risk/risk_engine.py
src/execution/execution_engine.py
src/storage/storage_engine.py


No other files may be created or modified.

Canonical Codex Instruction (COPY THIS EXACTLY)

Paste everything below into Codex as a single instruction.

ROLE:
You are acting as a junior Python developer.

GLOBAL OBJECTIVE:
Build a professional, teaching-first trading system skeleton.

PHASE:
PHASE 3 — Skeleton System (Teaching-First)

LOCAL OBJECTIVE (STEP 3.3):
Create minimal, self-contained skeleton modules for each core system component.

ALLOWED FILES TO MODIFY:
- src/scanner/scanner.py
- src/patterns/pattern_engine.py
- src/strategy/strategy_runner.py
- src/risk/risk_engine.py
- src/execution/execution_engine.py
- src/storage/storage_engine.py

REQUIREMENTS FOR EACH FILE:
1. Include a clear file-level docstring stating:
   - module purpose
   - Phase 3 skeleton status
   - absence of real logic
2. Define exactly one main class appropriate to the module.
3. Define one public method that:
   - prints teaching-style logs
   - returns an empty list, empty dict, or None
4. No imports from other project modules.
5. No trading logic or calculations.

FORBIDDEN:
- Do NOT wire modules together
- Do NOT import orchestrator
- Do NOT import IBKR or external libraries
- Do NOT simulate data

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Result After Merge & Pull

Each module file:

opens cleanly in PyCharm

imports without error

prints when its method is called

does nothing else

The system may not call them yet — that’s fine.

Definition of Done (STEP 3.3)

STEP 3.3 is DONE when:

All listed module files exist

All are valid Python

All print teaching logs

No cross-imports exist

Code merged via PR

No runtime errors on import

What Comes Next

After STEP 3.3:

STEP 3.4 — Wire Orchestrator to Module Skeletons

This will connect what we just created

Still no logic — only flow

Your next action

Copy the Canonical Codex Instruction above

Paste it into Codex

Let Codex create the Pull Request

Then come back and say:

“STEP 3.3 complete — PR created”

You are now working with excellent discipline and clarity.