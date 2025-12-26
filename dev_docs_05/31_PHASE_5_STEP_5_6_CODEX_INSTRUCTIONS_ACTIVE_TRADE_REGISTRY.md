# PHASE 5 — STRATEGY GOVERNANCE
## STEP 5.6 — ACTIVE TRADE REGISTRY (SINGLE SOURCE OF TRUTH)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **central Active Trade Registry** that becomes the
single source of truth for currently active trades across all strategies.

This step MUST be implemented in a way that:
- Resolves existing constructor conflicts
- Preserves orchestrator wiring
- Avoids breaking the teaching-first system

---

## GLOBAL OBJECTIVE

Create a deterministic, in-memory registry that:

- Tracks active trades by `symbol` and `trader_type`
- Is queried by the Risk Engine
- Is updated by the Execution Engine
- Persists across orchestrator cycles
- Replaces ALL internal trade counters

---

## FILES YOU ARE ALLOWED TO MODIFY

Modify **only** the following files:

- `src/core/active_trade_registry.py` (NEW FILE)
- `src/risk/risk_engine.py`
- `src/execution/execution_engine.py`
- `src/core/orchestrator.py` ⚠️ (REQUIRED to resolve constructor wiring)

Do NOT modify any other files.

---

## STEP 1 — CREATE ACTIVE TRADE REGISTRY

Create the file:

📄 `src/core/active_trade_registry.py`

Add EXACTLY the following code:

```python
class ActiveTradeRegistry:
    """
    Central registry tracking active trades by symbol and trader type.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._active_trades = []

    def register_trade(self, symbol: str, trader_type: str):
        self._active_trades.append(
            {"symbol": symbol, "trader_type": trader_type}
        )

    def unregister_trade(self, symbol: str, trader_type: str):
        self._active_trades = [
            t for t in self._active_trades
            if not (t["symbol"] == symbol and t["trader_type"] == trader_type)
        ]

    def count_active_by_trader(self, trader_type: str) -> int:
        return len(
            [t for t in self._active_trades if t["trader_type"] == trader_type]
        )

    def snapshot(self):
        return list(self._active_trades)
