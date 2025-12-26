"""
Execution engine skeleton illustrating where broker interactions would occur.

Phase 3: Skeleton status only — this module exists to teach structure.
No real broker calls, order management, or execution logic is implemented.
"""

from datetime import datetime
from typing import Optional

from domain.active_trade import ActiveTrade
from models.data_models import ExecutionResult, RiskDecision
from portfolio.active_trade_registry import active_trade_registry


class ExecutionEngine:
    """Minimal execution engine placeholder with teaching-first log statements."""

    def __init__(self, broker: Optional[object] = None) -> None:
        print("[BOOT] ExecutionEngine instantiated — phase 3 skeleton only")
        self.broker = broker

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
        strategy_name = getattr(risk_decision, "strategy_name", "UNKNOWN")
        direction = getattr(risk_decision, "direction", "UNKNOWN")
        print(
            f"[EXECUTION] Routing execution for symbol={symbol} to trader_type={trader_type} "
            "(teaching-only path)"
        )
        if getattr(risk_decision, "allowed", False):
            trade_id = f"{symbol}-{int(datetime.utcnow().timestamp())}"
            active_trade = ActiveTrade(
                trade_id=trade_id,
                symbol=symbol,
                strategy_name=strategy_name,
                trader_type=trader_type,
                direction=direction,
                quantity=getattr(risk_decision, "max_position_size", 0),
                entry_timestamp=datetime.utcnow(),
                status="OPEN",
            )
            active_trade_registry.register_trade(active_trade)
            print(
                "[EXECUTION] ActiveTrade registered trade_id="
                f"{trade_id} symbol={symbol} strategy={strategy_name} "
                f"trader_type={trader_type} direction={direction}"
            )
        else:
            print(
                "[EXECUTION] RiskDecision not allowed — skipping ActiveTrade creation; "
                "returning SIMULATED result only."
            )
        print("[EXECUTION] SIM mode active — no broker calls; returning simulated result.")

        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with no broker execution in SIM mode.",
        )
