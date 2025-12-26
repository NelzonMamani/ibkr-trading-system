# PHASE 5 — STRATEGY GOVERNANCE
## STEP 5.7 — TRADE LIFECYCLE: CLOSE & DEREGISTER ACTIVE TRADES

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce **explicit trade lifecycle closure**, allowing
active trades to be **closed and deregistered** from the Active Trade Registry.

This step completes the **minimum viable trade lifecycle**:
OPEN → ACTIVE → CLOSED.

---

## GLOBAL OBJECTIVE

You will:

- Add a deterministic, teaching-first mechanism to close trades
- Deregister closed trades from the ActiveTradeRegistry
- Allow capacity to free up across cycles
- Avoid broker integration or real PnL logic
- Preserve clarity, logging, and safety

This is NOT exit logic based on price.
This is **structural lifecycle management**.

---

## FILES YOU ARE ALLOWED TO MODIFY

Modify **only** the following files:

- `src/execution/execution_engine.py`
- `src/core/active_trade_registry.py`

Do NOT modify any other files.

---

## STEP 1 — EXTEND ACTIVE TRADE REGISTRY WITH CLOSE SUPPORT

Modify:

📄 `src/core/active_trade_registry.py`

Add the following method:

```python
def close_all_trades(self):
    """
    Teaching-first lifecycle reset.
    Closes all active trades deterministically.
    """
    closed = list(self._active_trades)
    self._active_trades.clear()
    return closed
