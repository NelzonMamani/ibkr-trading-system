"""
Execution engine skeleton illustrating where broker interactions would occur.

Phase 3: Skeleton status only — this module exists to teach structure.
No real broker calls, order management, or execution logic is implemented.
"""

from typing import Optional

from config.runtime_config import RunMode, get_run_mode
from core.active_trade_registry import ActiveTradeRegistry, ActiveTrade
from core.event_collector import EventCollector
from models.data_models import ExecutionResult, RiskDecision
from sim.price_feed import DeterministicPriceFeed


class ExecutionEngine:
    """Minimal execution engine placeholder with teaching-first log statements."""

    def __init__(
        self,
        broker: Optional[object] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[DeterministicPriceFeed] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — phase 3 skeleton only")
        self.broker = broker
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.current_tick: Optional[int] = None
        self.run_mode: RunMode = get_run_mode()

    def execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
        """
        Demonstrate how a risk decision could lead to an execution call.

        Returns an ExecutionResult to highlight routing while emitting clear instructional logs
        about the intended behavior without touching any broker.
        """

        print("[EXECUTION] Received risk decision for teaching-only execution flow")
        if risk_decision is None:
            print("[EXECUTION] No execution performed — placeholder path")
            return ExecutionResult(
                symbol="UNKNOWN",
                trader_type="MANUAL",
                attempted=False,
                status="SKIPPED",
                rationale="No risk decision provided; nothing to execute in teaching mode.",
            )

        trader_type = getattr(risk_decision, "trader_type", "MANUAL")
        symbol = getattr(risk_decision, "symbol", "UNKNOWN")
        direction = getattr(risk_decision, "direction", "UNKNOWN")
        strategy_name = getattr(risk_decision, "strategy_name", "UNKNOWN")
        quantity = getattr(risk_decision, "max_position_size", 1)
        print(
            "[EXECUTION:REGISTRY] Current active trades snapshot by trader_type "
            f"{trader_type}: {self.trade_registry.count_active_by_trader(trader_type)}"
        )
        if not getattr(risk_decision, "allowed", True):
            print(
                "[EXECUTION] Risk decision not allowed — skipping registration in registry"
            )
            return ExecutionResult(
                symbol=symbol,
                trader_type=trader_type,
                attempted=False,
                status="BLOCKED",
                rationale=(
                    "Risk engine blocked this trade; no execution attempted in "
                    "teaching-only mode."
                ),
                direction=direction,
                quantity=quantity,
            )

        print(
            f"[EXECUTION] Routing execution for symbol={symbol} to trader_type={trader_type} "
            "(teaching-only path)"
        )
        tick = self.current_tick if self.current_tick is not None else 0
        entry_price = self.price_feed.price_for(symbol, tick)
        active_trade = ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=tick,
            entry_price=entry_price,
            direction=direction,
            quantity=quantity,
            strategy_name=strategy_name,
        )
        self.trade_registry.register_trade(active_trade)
        self.event_collector.emit(
            event_type="TRADE_OPENED",
            source="ExecutionEngine",
            payload={
                "symbol": risk_decision.symbol,
                "trader_type": risk_decision.trader_type,
                "strategy_name": strategy_name,
                "entry_tick": tick,
                "opened_at_tick": tick,
                "entry_price": entry_price,
                "mode": self.run_mode.value,
                "direction": direction,
                "quantity": quantity,
            },
        )
        print(
            f"[EVENT] TRADE_OPENED emitted for "
            f"{risk_decision.symbol} ({risk_decision.trader_type})"
            f" tick={tick} price={entry_price}"
        )
        print(
            "[EXECUTION:REGISTRY] Registered active trade "
            f"symbol={symbol} trader_type={trader_type}"
        )
        print(
            "[EXECUTION:REGISTRY] Active trades for trader_type "
            f"{trader_type}: {self.trade_registry.count_active_by_trader(trader_type)}"
        )
        print(
            f"[EXECUTION] {self.run_mode.value} mode active — no broker calls; returning simulated result."
        )
        if self.run_mode == RunMode.SIM:
            print(
                f"[EXECUTION] Simulating trade CLOSE for "
                f"{risk_decision.symbol} ({risk_decision.trader_type})"
            )
            close_tick = self.current_tick if self.current_tick is not None else 0
            close_price = self.price_feed.price_for(symbol, close_tick)
            trade = self.trade_registry.get_trade(symbol, trader_type)
            entry_tick = trade.entry_tick if trade else tick
            entry_price_for_pnl = trade.entry_price if trade else entry_price
            realised_pnl = round(close_price - entry_price_for_pnl, 2)
            self.trade_registry.mark_closed(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                close_tick=close_tick,
                close_price=close_price,
                realised_pnl=realised_pnl,
            )
            print(
                f"[EXECUTION] CLOSE symbol={symbol} tick={close_tick} "
                f"close_price={close_price} realised_pnl={realised_pnl} (SIM)"
            )
            self.event_collector.emit(
                event_type="TRADE_CLOSED",
                source="ExecutionEngine",
                payload={
                    "symbol": risk_decision.symbol,
                    "trader_type": risk_decision.trader_type,
                    "strategy_name": getattr(trade, "strategy_name", strategy_name),
                    "entry_tick": entry_tick,
                    "opened_at_tick": entry_tick,
                    "entry_price": entry_price_for_pnl,
                    "close_tick": close_tick,
                    "close_price": close_price,
                    "closed_at_tick": close_tick,
                    "exit_price": close_price,
                    "pnl": realised_pnl,
                    "realised_pnl": realised_pnl,
                    "mode": self.run_mode.value,
                    "exit_tick": close_tick,
                },
            )
            print(
                f"[EVENT] TRADE_CLOSED emitted for "
                f"{risk_decision.symbol} ({risk_decision.trader_type}) "
                f"tick={close_tick} price={close_price} pnl={realised_pnl}"
            )
            self.trade_registry.unregister_trade(
                symbol=risk_decision.symbol, trader_type=risk_decision.trader_type
            )
            print(
                f"[EXECUTION:REGISTRY] Unregistered trade "
                f"{risk_decision.symbol} ({risk_decision.trader_type})"
            )
        else:
            print(
                "[EXECUTION] Non-SIM mode detected — skipping deterministic SIM close flow."
            )

        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with no broker execution in SIM mode.",
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            entry_tick=tick,
        )

    def complete_trade(self, symbol: str, trader_type: str) -> None:
        """
        Teaching helper to remove an active trade when a lifecycle ends.

        No broker integration; purely updates the in-memory registry.
        """

        self.trade_registry.unregister_trade(symbol, trader_type)
        print(
            "[EXECUTION:REGISTRY] Completed trade "
            f"symbol={symbol} trader_type={trader_type}; "
            f"remaining active={self.trade_registry.count_active_by_trader(trader_type)}"
        )

    def close_all_active_trades(self):
        """
        Teaching-first lifecycle reset.

        Closes and deregisters all active trades so capacity is freed in the
        ActiveTradeRegistry for future cycles.
        """

        closed_trades = self.trade_registry.close_all_trades()
        if not closed_trades:
            print("[EXECUTION:REGISTRY] No active trades to close — registry already empty.")
            return []

        print("[EXECUTION:REGISTRY] Closing all active trades and resetting registry")
        for trade in closed_trades:
            print(
                "[EXECUTION:REGISTRY] Closed trade "
                f"symbol={getattr(trade, 'symbol', 'UNKNOWN')} "
                f"trader_type={getattr(trade, 'trader_type', 'UNKNOWN')}"
            )

        print(
            "[EXECUTION:REGISTRY] All trades closed; registry capacity reset for next cycle"
        )
        return closed_trades
