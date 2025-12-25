diff --git a/src/execution/execution_engine.py b/src/execution/execution_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..e815f15b819fd7b0a69b6bbf948ea6ad940124e5
--- /dev/null
+++ b/src/execution/execution_engine.py
@@ -0,0 +1,39 @@
+# Filename: execution_engine.py
+# Timestamp: YYYY-MM-DD HH:MM:SS
+# Version: Phase 3.1 skeleton — execution engine only, no logic
+
+"""
+Execution engine skeleton responsible for interacting with the broker via a BrokerInterface.
+
+Responsibility:
+- Define the interface to execute trades based on RiskDecision inputs.
+- Provide teaching-first logging for submission intent and placeholder outcomes.
+
+Deliberately NOT doing in Phase 3:
+- No broker connectivity or order placement.
+- No fill handling, retries, or error mapping.
+- No trade lifecycle management beyond placeholder logging.
+"""
+
+from typing import Optional
+
+from broker.broker_interface import BrokerInterface
+from models.data_models import ExecutionResult, RiskDecision
+
+
+class ExecutionEngine:
+    """Skeleton execution engine demonstrating broker interaction points."""
+
+    def __init__(self, broker: Optional[BrokerInterface] = None) -> None:
+        print("[BOOT] ExecutionEngine instantiated — skeleton only")
+        self.broker = broker
+
+    def execute_trade(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
+        """Execute a trade placeholder; returns None when no action taken."""
+
+        print("[EXECUTION] Skeleton execution invoked — no broker calls performed")
+        if risk_decision.risk_decision is None:
+            print("[EXECUTION] No action — risk decision undefined in skeleton")
+            return None
+
+        return ExecutionResult(trade_id=risk_decision.trade_id, order_status=None)
