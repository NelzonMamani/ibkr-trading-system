# PHASE 6 — EVENT-DRIVEN ARCHITECTURE
## STEP 6.8 — TRADE CLOSE EVENTS (LIFECYCLE COMPLETION)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce **explicit TRADE_CLOSED events**
to complete the trade lifecycle.

This step simulates trade closure.
No PnL yet. No broker logic.

---

## GLOBAL OBJECTIVE

You will:

- Emit TRADE_CLOSED events
- Unregister trades from ActiveTradeRegistry
- Preserve deterministic, teaching-first behavior
- Simulate closure in SIM mode only
- Add clear teaching prints

---

## FILES TO MODIFY

Modify **only**:

- `src/execution/execution_engine.py`

---

## STEP 1 — ADD SIMULATED TRADE CLOSURE

Inside `ExecutionEngine.execute_trade()` (or equivalent loop):

After emitting TRADE_OPENED and returning a SIMULATED result,
add a **simulated close step**:

```python
print(
    f"[EXECUTION] Simulating trade CLOSE for "
    f"{risk_decision.symbol} ({risk_decision.trader_type})"
)
```

---

## STEP 2 — UNREGISTER FROM REGISTRY

Immediately after the simulated close print, call:

```python
self.trade_registry.unregister_trade(
    symbol=risk_decision.symbol,
    trader_type=risk_decision.trader_type
)
```

Add a print:

```python
print(
    f"[EXECUTION:REGISTRY] Unregistered trade "
    f"{risk_decision.symbol} ({risk_decision.trader_type})"
)
```

---

## STEP 3 — EMIT TRADE_CLOSED EVENT

Import SystemEvent if not already imported:

```python
from core.system_event import SystemEvent
```

Emit:

```python
self.event_collector.record(
    SystemEvent(
        event_type="TRADE_CLOSED",
        source="ExecutionEngine",
        payload={
            "symbol": risk_decision.symbol,
            "trader_type": risk_decision.trader_type,
            "mode": "SIM"
        }
    )
)
```

Add print:

```python
print(
    f"[EVENT] TRADE_CLOSED emitted for "
    f"{risk_decision.symbol} ({risk_decision.trader_type})"
)
```

---

## VALIDATION REQUIREMENTS

After implementation:

- TRADE_OPENED is followed by TRADE_CLOSED
- Registry count returns to zero by cycle end
- No trade remains active after execution
- Event summary includes TRADE_CLOSED
- Determinism preserved

---

## COMPLETION CRITERIA

This step is complete when:

- Trade lifecycle is OPEN → CLOSED
- Registry state is clean after cycle
- Events reflect full lifecycle

---

## ✅ NEXT ACTION

1. Copy entire file
2. Paste into Codex
3. Run one cycle
4. Verify TRADE_CLOSED events appear

Reply with:

> **“STEP 6.8 complete — trade lifecycle closed”**
