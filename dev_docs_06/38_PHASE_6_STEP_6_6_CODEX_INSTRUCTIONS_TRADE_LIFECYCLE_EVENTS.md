# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.6 — TRADE LIFECYCLE EVENTS (OPEN / BLOCKED)

You are Codex operating on the IBKR Trading System repository.

Your task is to emit **explicit trade lifecycle events**
so every trade decision is auditable via the event system.

This step does NOT close trades yet.
It introduces OPEN vs BLOCKED semantics.

---

## GLOBAL OBJECTIVE

You will:

- Emit TRADE_OPENED when execution registers a trade
- Emit TRADE_BLOCKED when risk blocks a trade
- Preserve all existing logic
- Keep behavior deterministic
- Add verbose prints for teaching clarity

---

## FILES TO MODIFY

Modify **only**:

- `src/risk/risk_engine.py`
- `src/execution/execution_engine.py`

---

## STEP 1 — EMIT TRADE_BLOCKED EVENTS (RISK)

In `risk_engine.py`:

1. Import SystemEvent:

```python
from core.system_event import SystemEvent
```

2. When a trade is BLOCKED, emit:

```python
self.event_collector.record(
    SystemEvent(
        event_type="TRADE_BLOCKED",
        source="RiskEngine",
        payload={
            "symbol": trade_intent.symbol,
            "trader_type": trade_intent.trader_type,
            "reason": "strategy_limit"
        }
    )
)
```

Add a print:

```python
print(
    f"[EVENT] TRADE_BLOCKED emitted for "
    f"{trade_intent.symbol} ({trade_intent.trader_type})"
)
```

⚠️ Emit **only when allowed=False**.

---

## STEP 2 — EMIT TRADE_OPENED EVENTS (EXECUTION)

In `execution_engine.py`:

1. Import SystemEvent:

```python
from core.system_event import SystemEvent
```

2. After successful registration in ActiveTradeRegistry, emit:

```python
self.event_collector.record(
    SystemEvent(
        event_type="TRADE_OPENED",
        source="ExecutionEngine",
        payload={
            "symbol": risk_decision.symbol,
            "trader_type": risk_decision.trader_type,
            "mode": "SIM"
        }
    )
)
```

Add a print:

```python
print(
    f"[EVENT] TRADE_OPENED emitted for "
    f"{risk_decision.symbol} ({risk_decision.trader_type})"
)
```

---

## VALIDATION REQUIREMENTS

After implementation:

- BLOCKED trades emit TRADE_BLOCKED
- Allowed trades emit TRADE_OPENED
- Event summary increases accordingly
- Order remains deterministic
- No duplicate lifecycle events

---

## COMPLETION CRITERIA

This step is complete when:

- Trade lifecycle is visible via events
- Registry state aligns with lifecycle events
- System remains stable

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run 2 cycles
4. Confirm TRADE_BLOCKED and TRADE_OPENED events appear

Reply with:

> **“STEP 6.6 complete — trade lifecycle events emitted”**
