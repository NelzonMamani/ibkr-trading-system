# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.1 — INTRODUCE SYSTEM EVENT MODEL (FOUNDATION)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **lightweight, teaching-first Event Model**
that allows the system to emit and observe structured events
without changing core execution flow.

This is the foundation for:
- Observability
- Auditing
- Metrics
- Replay
- Future async processing

This is NOT a messaging system.
This is an **event log abstraction**.

---

## GLOBAL OBJECTIVE

You will:

- Define a simple Event data structure
- Emit events at key system lifecycle stages
- Preserve deterministic, synchronous execution
- Avoid message brokers, queues, or async frameworks
- Keep the system readable and debuggable

---

## FILES YOU ARE ALLOWED TO MODIFY

You must modify **only** the following files:

- `src/core/events.py` (NEW FILE)
- `src/core/orchestrator.py`

Do NOT modify any other files.

---

## STEP 1 — CREATE EVENT MODEL

Create a new file:

📄 `src/core/events.py`

Add the following implementation:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class SystemEvent:
    event_type: str
    source: str
    payload: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()
```

Design notes:
- Events are immutable
- In-memory only
- No side effects
- Serializable later (not now)

---

## STEP 2 — EMIT EVENTS FROM ORCHESTRATOR

Modify:

📄 `src/core/orchestrator.py`

### A) Import the event model

At the top of the file, add:

```python
from core.events import SystemEvent
```

---

### B) Emit lifecycle events inside `run_once()`

Add the following `print(SystemEvent(...))` calls
at the indicated points in `run_once()`.

#### 1️⃣ Cycle start

At the beginning of `run_once()`:

```python
print(SystemEvent(
    event_type="CYCLE_START",
    source="Orchestrator",
    payload={"run_mode": self.run_mode}
))
```

---

#### 2️⃣ After scanner completes

Immediately after the scanner stage finishes:

```python
print(SystemEvent(
    event_type="SCAN_COMPLETE",
    source="Scanner",
    payload={"candidates": len(scanner_output)}
))
```

---

#### 3️⃣ After strategy stage completes

Immediately after strategies generate trade intents:

```python
print(SystemEvent(
    event_type="STRATEGY_COMPLETE",
    source="StrategyRunner",
    payload={"trade_intents": len(strategy_output)}
))
```

---

#### 4️⃣ After execution stage completes

Immediately after execution finishes:

```python
print(SystemEvent(
    event_type="EXECUTION_COMPLETE",
    source="ExecutionEngine",
    payload={"results": len(execution_output)}
))
```

---

## DESIGN CONSTRAINTS (STRICT)

- Events must NOT affect control flow
- No observers, listeners, or handlers yet
- No registries
- No async logic
- Printing is sufficient
- System behavior must remain unchanged

---

## VALIDATION REQUIREMENTS

After implementation:

- Each cycle prints structured `SystemEvent` objects
- Events appear in chronological order
- No logic or timing changes occur
- The system remains deterministic

---

## COMPLETION CRITERIA

This step is complete when:

- Events are emitted at all defined points
- Output shows structured event objects
- No regressions occur
- No new dependencies are introduced

---

## ✅ WHAT YOU MUST DO NEXT

1. Copy **this entire Markdown file**
2. Paste it directly into **Codex**
3. Let Codex implement the changes
4. Run the system
5. Verify event objects appear in logs

When complete, reply with:

> **“STEP 6.1 complete — event model online”**

Do NOT proceed to the next step until this is verified.
