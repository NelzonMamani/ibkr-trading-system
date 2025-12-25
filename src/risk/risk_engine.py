diff --git a/src/risk/risk_engine.py b/src/risk/risk_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d6fe5fb550c927598a9f2768312c644406f24015
--- /dev/null
+++ b/src/risk/risk_engine.py
@@ -0,0 +1,31 @@
+# Filename: risk_engine.py
+# Timestamp: YYYY-MM-DD HH:MM:SS
+# Version: Phase 3.1 skeleton — risk engine only, no logic
+
+"""
+Risk engine skeleton responsible for approving or blocking trade intents.
+
+Responsibility:
+- Define the interface to evaluate TradeIntent objects and return RiskDecision outcomes.
+- Provide explicit logging for approvals or blocks to teach downstream flow expectations.
+
+Deliberately NOT doing in Phase 3:
+- No risk calculations, sizing rules, or circuit breaker logic.
+- No account state checks or compliance validations.
+- No integration with broker or storage systems.
+"""
+
+from models.data_models import RiskDecision, TradeIntent
+
+
+class RiskEngine:
+    """Skeleton risk engine returning placeholder decisions with logging."""
+
+    def __init__(self) -> None:
+        print("[BOOT] RiskEngine instantiated — skeleton only")
+
+    def evaluate_trade_intent(self, trade_intent: TradeIntent) -> RiskDecision:
+        """Evaluate a trade intent placeholder and return a neutral RiskDecision."""
+
+        print("[RISK] Skeleton risk evaluation invoked — no logic implemented yet")
+        return RiskDecision(trade_id=trade_intent.trade_id, risk_decision=None)
