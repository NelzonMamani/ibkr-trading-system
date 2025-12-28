# PHASE 8 — TRADE LIFECYCLE & EXIT ENGINE
## STEP 8.1 — INTRODUCE TEACHING-FIRST TRADE EXIT ENGINE

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce a **Trade Exit Engine** that explicitly manages
the lifecycle of open trades in LIVE and PAPER modes.

This step resolves the intentional Phase 7 behavior where trades remain open
indefinitely and prepares the system for realistic lifecycle management.

This must be teaching-first, deterministic, and safe.

---

## OBJECTIVE

You will:

- Introduce an explicit TradeExitEngine
- Close active trades using simple, explainable rules
- Ensure ActiveTradeRegistry is updated correctly on trade close
- Preserve correct behavior across SIM, PAPER, and LIVE modes
- Avoid broker integration or real market exits
- Prepare the system structurally for Phase 8.2+ extensions

---

## FILES TO MODIFY

You must modify **only** the following files:

- `src/execution/trade_exit_engine.py` (NEW FILE)
- `src/core/orchestrator.py`
- `src/execution/execution_engine.py`

Do not modify any other files.

---

## STEP 1 — CREATE TRADE EXIT ENGINE

Create a new file:

📄 `src/execution/trade_exit_engine.py`

Add the following implementation:

```python
from typing import List
from core.active_trade_registry import ActiveTradeRegistry
from execution.execution_models import ExecutionResult
from events.system_events import SystemEvent
from datetime import datetime


class TradeExitEngine:
    """
    Teaching-first engine responsible for closing active trades explicitly.

    This engine exists to make trade lifecycle management visible,
    intentional, and extendable.
    """

    def __init__(self, trade_registry: ActiveTradeRegistry, event_collector):
        self.trade_registry = trade_registry
        self.event_collector = event_collector

    def evaluate_and_close_trades(self, run_mode: str, tick: int) -> List[ExecutionResult]:
        """
        Evaluate open trades and close them using simple teaching rules.

        Current teaching rule:
        - In SIM: do nothing (SIM auto-close already handled)
        - In LIVE / PAPER: close all trades after 1 tick
        """

        results = []

        if run_mode == "SIM":
            return results

        active_trades = self.trade_registry.snapshot()

        for trade in active_trades:
            symbol = trade["symbol"]
            trader_type = trade["trader_type"]

            # Teaching-only exit logic
            self.trade_registry.unregister_trade(symbol, trader_type)

            self.event_collector.record(
                SystemEvent(
                    event_type="TRADE_CLOSED",
                    source="TradeExitEngine",
                    payload={
                        "symbol": symbol,
                        "trader_type": trader_type,
                        "tick": tick,
                        "reason": "Teaching exit after 1 tick"
                    },
                    timestamp=datetime.utcnow(),
                )
            )

            results.append(
                ExecutionResult(
                    symbol=symbol,
                    trader_type=trader_type,
                    attempted=True,
                    status="CLOSED",
                    rationale="Teaching-only exit via TradeExitEngine"
                )
            )

        return results
