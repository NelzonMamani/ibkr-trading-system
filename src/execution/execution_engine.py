"""
Execution engine skeleton illustrating where broker interactions would occur.

Phase 3: Skeleton status only — this module exists to teach structure.
No real broker calls, order management, or execution logic is implemented.
"""

from typing import Optional

from models.data_models import ExecutionResult, RiskDecision


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
        print(
            f"[EXECUTION] Routing execution for symbol={symbol} to trader_type={trader_type} "
            "(teaching-only path)"
        )
        print("[EXECUTION] SIM mode active — no broker calls; returning simulated result.")

        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=True,
            status="SIMULATED",
            rationale="Teaching-only: routed by trader_type with no broker execution in SIM mode.",
        )
