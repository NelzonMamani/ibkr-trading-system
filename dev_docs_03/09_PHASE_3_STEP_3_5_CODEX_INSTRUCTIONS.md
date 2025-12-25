PHASE 3 — STEP 3.5 Codex Instructions (Skeleton Trade Record & Storage Flow)
Purpose

STEP 3.5 introduces a minimal trade record data model and wires it into the orchestrator and storage engine.

This step answers the question:

“If a trade were to happen, what would we store — structurally — without doing anything yet?”

No trading logic.
No persistence logic.
Only shape, intent, and flow.

Phase Context

Phase: PHASE 3 — Skeleton System (Restarted)

Step: STEP 3.5 — Skeleton Trade Record & Storage Flow

Mode: Teaching-First

Risk Level: Low (data shape only)

Local Objective (STEP 3.5)

Define a minimal TradeRecord data model and pass it from the Core Orchestrator into the Storage Engine as a placeholder.

What This Step MUST Do
1. Introduce a TradeRecord data model

Lives in a dedicated file (models)

Contains only:

scanner output

pattern output

strategy output

risk output

execution output

No behaviour

No validation

No persistence logic

2. Update Core Orchestrator

Create a TradeRecord after execution stage

Pass it to StorageEngine

Print teaching logs

3. Update Storage Engine

Accept a TradeRecord

Print that it was “received”

Return a placeholder acknowledgement

What This Step MUST NOT Do

No real database

No file writes

No validation rules

No analytics

No learning logic

No timestamps

No IDs

Allowed Files to Modify
src/models/data_models.py
src/core/orchestrator.py
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

LOCAL OBJECTIVE (STEP 3.5):
Introduce a minimal TradeRecord data model and pass it through the Core Orchestrator
into the Storage Engine as a placeholder.

ALLOWED FILES TO MODIFY:
- src/models/data_models.py
- src/core/orchestrator.py
- src/storage/storage_engine.py

REQUIREMENTS — data_models.py:
1. Define a TradeRecord class.
2. Use a simple Python class or dataclass.
3. Fields should include:
   - scanner_output
   - pattern_output
   - strategy_output
   - risk_output
   - execution_output
4. Include a file-level docstring explaining:
   - this is a Phase 3 skeleton
   - no logic exists
   - shape only

REQUIREMENTS — core/orchestrator.py:
1. After execution stage, create a TradeRecord instance.
2. Populate it using placeholder outputs from each stage.
3. Pass the TradeRecord to the StorageEngine.
4. Add teaching-style logs explaining why this record exists.

REQUIREMENTS — storage/storage_engine.py:
1. Accept a TradeRecord object in a public method.
2. Print that the record was received.
3. Return a placeholder acknowledgement (e.g. True or None).

FORBIDDEN:
- Do NOT implement persistence
- Do NOT add validation
- Do NOT add IDs or timestamps
- Do NOT add trading logic

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO git diff format
- NO + / - lines
- NO explanations outside code

STOP CONDITION:
If any requirement is unclear, ask before generating code.

Expected Runtime Output (Conceptual)

After merge, pull, and run:

[DATA] TradeRecord created — skeleton placeholder
[STORAGE] TradeRecord received for teaching-only storage
[STORAGE] No persistence performed — placeholder acknowledgement


Exact wording may differ; intent must be clear.

Definition of Done (STEP 3.5)

STEP 3.5 is DONE when:

TradeRecord class exists

Orchestrator creates a TradeRecord

StorageEngine receives it

All steps print teaching logs

No persistence logic exists

System runs cleanly

What Comes After (FINAL STEP)

After STEP 3.5:

STEP 3.6 — Phase 3 Freeze & Validation


This will formally lock Phase 3 and prepare for Phase 4 (minimal live-capable system).

Your next action

Copy the Canonical Codex Instruction above

Paste it into Codex

Let Codex create the Pull Request

Then come back and say:

“STEP 3.5 complete — PR created”

You are doing exceptionally well — this is now a real system skeleton.