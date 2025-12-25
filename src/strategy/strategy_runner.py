diff --git a/src/strategy/strategy_runner.py b/src/strategy/strategy_runner.py
new file mode 100644
index 0000000000000000000000000000000000000000..b59b3e2dc89213fa42a88c13f9d2ebd305e080e1
--- /dev/null
+++ b/src/strategy/strategy_runner.py
@@ -0,0 +1,33 @@
+# Filename: strategy_runner.py
+# Timestamp: YYYY-MM-DD HH:MM:SS
+# Version: Phase 3.1 skeleton — strategy runner only, no logic
+
+"""
+Strategy runner skeleton responsible for converting pattern evaluations into trade intent.
+
+Responsibility:
+- Define the interface for generating TradeIntent objects from PatternResult inputs.
+- Provide teaching-first logging describing neutral or intent-producing outcomes.
+
+Deliberately NOT doing in Phase 3:
+- No strategy rules, scoring, or position sizing logic.
+- No trade direction decisions beyond placeholder values.
+- No integration with real-time data or broker state.
+"""
+
+from typing import List
+
+from models.data_models import PatternResult, TradeIntent
+
+
+class StrategyRunner:
+    """Skeleton strategy runner returning empty intents with instructional logs."""
+
+    def __init__(self) -> None:
+        print("[BOOT] StrategyRunner instantiated — skeleton only")
+
+    def generate_trade_intent(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
+        """Generate trade intents placeholder from pattern results."""
+
+        print("[STRATEGY] Skeleton strategy runner invoked — no logic implemented yet")
+        return []
