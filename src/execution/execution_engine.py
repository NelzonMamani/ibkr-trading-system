"""
Execution engine skeleton responsible for interacting with the broker via a BrokerInterface.
"""

from typing import Optional

from broker.broker_interface import BrokerInterface
from models.data_models import ExecutionResult, RiskDecision


class ExecutionEngine:
    """Skeleton execution engine demonstrating broker interaction points."""

    def __init__(self, broker: Optional[BrokerInterface] = None) -> None:
        print("[BOOT] ExecutionEngine instantiated — skeleton only")
        self.broker = broker

    def execute_trade(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        """Execute a trade placeholder; returns None when no action taken."""

        print("[EXECUTION] Skeleton execution invoked — no broker calls performed")
        if risk_decision.risk_decision is None:
            print("[EXECUTION] No action — risk decision undefined in skeleton")
            return None

        return ExecutionResult(trade_id=risk_decision.trade_id, order_status=None)
