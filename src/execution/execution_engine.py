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
from execution.slippage_model import SlippageModel
from execution.liquidity_model import LiquidityModel


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

        This engine is authoritative for opening trades. Closures are delegated to
        TradeExitEngine to maintain a single execution path.
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
        stop_loss_price = getattr(risk_decision, "stop_loss_price", None)
        take_profit_price = getattr(risk_decision, "take_profit_price", None)
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
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
            )

        print(
            f"[EXECUTION] Routing execution for symbol={symbol} to trader_type={trader_type} "
            "(teaching-only path)"
        )
        tick = self.current_tick if self.current_tick is not None else 0
        requested_quantity = max(
            1, int(getattr(risk_decision, "max_position_size", 1) or 1)
        )
        available_liquidity = LiquidityModel.available_liquidity(
            symbol=symbol,
            tick=tick,
            trader_type=trader_type,
        )
        filled_quantity = min(requested_quantity, available_liquidity)
        remaining_quantity = max(0, requested_quantity - filled_quantity)
        fill_status = "NONE"
        if filled_quantity == requested_quantity and requested_quantity > 0:
            fill_status = "FULL"
        elif 0 < filled_quantity < requested_quantity:
            fill_status = "PARTIAL"
        raw_price = self.price_feed.price_for(symbol, tick)

        if filled_quantity == 0:
            reason = (
                "LIQUIDITY_ZERO" if available_liquidity == 0 else "LIQUIDITY_CAP"
            )
            print(
                "[LIQUIDITY] "
                f"symbol={symbol} tick={tick} trader_type={trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                "status=NONE (no trade opened)"
            )
            self.event_collector.emit(
                event_type="TRADE_NOT_FILLED",
                source="ExecutionEngine",
                payload={
                    "symbol": symbol,
                    "trader_type": trader_type,
                    "tick": tick,
                    "requested_quantity": requested_quantity,
                    "available_liquidity": available_liquidity,
                    "filled_quantity": 0,
                    "remaining_quantity": remaining_quantity,
                    "reason": reason,
                    "fill_status": "NONE",
                },
            )
            return ExecutionResult(
                symbol=symbol,
                trader_type=trader_type,
                attempted=True,
                status="NOT_FILLED",
                rationale="Deterministic liquidity returned zero available volume.",
                direction=direction,
                quantity=0,
                entry_price=None,
                raw_price=raw_price,
                entry_tick=tick,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                requested_quantity=requested_quantity,
                filled_quantity=0,
                remaining_quantity=remaining_quantity,
                fill_status="NONE",
                average_fill_price=None,
                note="No fill: liquidity zero for this tick/symbol combination.",
            )

        entry_price = SlippageModel.apply_slippage(
            price=raw_price,
            direction=direction,
            trader_type=trader_type,
            quantity=filled_quantity,
        )
        slippage_applied = round(entry_price - raw_price, 2)
        active_trade = ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=tick,
            entry_price=entry_price,
            direction=direction,
            quantity=filled_quantity,
            strategy_name=strategy_name,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
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
                "raw_price": raw_price,
                "slippage_applied": slippage_applied,
                "execution_price": entry_price,
                "mode": self.run_mode.value,
                "direction": direction,
                "quantity": filled_quantity,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "requested_quantity": requested_quantity,
                "filled_quantity": filled_quantity,
                "remaining_quantity": remaining_quantity,
                "fill_status": fill_status,
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

        liquidity_note = None
        if fill_status == "PARTIAL":
            liquidity_note = "Partial fill due to deterministic liquidity cap."
            print(
                "[LIQUIDITY] "
                f"symbol={symbol} tick={tick} trader_type={trader_type} "
                f"requested={requested_quantity} available={available_liquidity} "
                f"filled={filled_quantity} remaining={remaining_quantity} "
                f"status=PARTIAL"
            )

        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with no broker execution in SIM mode.",
            direction=direction,
            quantity=filled_quantity,
            entry_price=entry_price,
            raw_price=raw_price,
            slippage_applied=slippage_applied,
            entry_tick=tick,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            fill_status=fill_status,
            average_fill_price=entry_price,
            note=liquidity_note,
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

    def shutdown(self) -> None:
        """
        Idempotent shutdown placeholder.

        Future implementation will release broker resources, cancel orders,
        and flush telemetry. For now this acts as a structural hook to enable
        safe orchestrator shutdown sequencing.
        """

        print("[EXECUTION] Shutdown requested — placeholder cleanup complete.")
