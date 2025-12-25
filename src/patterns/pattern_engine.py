diff --git a/src/patterns/pattern_engine.py b/src/patterns/pattern_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..b2aabe201850f97c3e5d8a4f428d11c8b6e27b29
--- /dev/null
+++ b/src/patterns/pattern_engine.py
@@ -0,0 +1,33 @@
+# Filename: pattern_engine.py
+# Timestamp: YYYY-MM-DD HH:MM:SS
+# Version: Phase 3.1 skeleton — pattern engine only, no logic
+
+"""
+Pattern engine skeleton responsible for evaluating scanner candidates for known patterns.
+
+Responsibility:
+- Provide the interface for pattern evaluation returning PatternResult objects.
+- Maintain teaching-first logging for detected or rejected patterns.
+
+Deliberately NOT doing in Phase 3:
+- No pattern detection calculations or indicator usage.
+- No trading decisions or confidence scoring logic.
+- No integration with data sources or historical candles.
+"""
+
+from typing import List
+
+from models.data_models import PatternResult, ScannerResult
+
+
+class PatternEngine:
+    """Skeleton pattern engine that mirrors the interface without logic."""
+
+    def __init__(self) -> None:
+        print("[BOOT] PatternEngine instantiated — skeleton only")
+
+    def evaluate_patterns(self, scanner_results: List[ScannerResult]) -> List[PatternResult]:
+        """Evaluate patterns for provided scanner results placeholder."""
+
+        print("[PATTERN] Skeleton pattern evaluation invoked — no logic implemented yet")
+        return []
