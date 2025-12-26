"""
Execution engine skeleton illustrating where broker interactions would occur.

Phase 3: Skeleton status only — this module exists to teach structure.
No real broker calls, order management, or execution logic is implemented.
"""

from typing import Optional

from core.active_trade_registry import ActiveTradeRegistry
from models.data_models import ExecutionResult, RiskDecision


class ExecutionEngine:
    """Minimal execution engine placeholder with teaching-first log statements."""

    def __init__(
        self,
        broker: Optional[object] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — phase 3 skeleton only")
        self.broker = broker
        self.trade_registry = trade_registry or ActiveTradeRegistry()

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
            )

        print(
            f"[EXECUTION] Routing execution for symbol={symbol} to trader_type={trader_type} "
            "(teaching-only path)"
        )
        self.trade_registry.register_trade(symbol, trader_type)
        print(
            "[EXECUTION:REGISTRY] Registered active trade "
            f"symbol={symbol} trader_type={trader_type}"
        )
        print(
            "[EXECUTION:REGISTRY] Active trades for trader_type "
            f"{trader_type}: {self.trade_registry.count_active_by_trader(trader_type)}"
        )
        print("[EXECUTION] SIM mode active — no broker calls; returning simulated result.")

        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with no broker execution in SIM mode.",
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
