# File: logging_framework_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Logging & telemetry framework skeleton

"""
LOGGING & TELEMETRY FRAMEWORK
-----------------------------

GLOBAL CONTEXT
--------------
This file defines the **central logging and telemetry framework**.

Every module must log through this interface.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_23_OUTCOME_LOGGING_AND_TELEMETRY.md

STANDALONE GUARANTEE
-------------------
This file can be used independently for testing.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from datetime import datetime
from typing import Optional

# ================================
# 2. Logger Class
# ================================

class Logger:
    """
    Logger
    ------
    Centralized, human-readable logger.
    """

    def __init__(self, name: str):
        self.name = name

    # ================================
    # 3. Logging Methods
    # ================================

    def info(self, message: str, context: Optional[dict] = None):
        self._emit("INFO", message, context)

    def warn(self, message: str, context: Optional[dict] = None):
        self._emit("WARN", message, context)

    def error(self, message: str, context: Optional[dict] = None):
        self._emit("ERROR", message, context)

    def recovery(self, message: str, context: Optional[dict] = None):
        self._emit("RECOVERY", message, context)

    def pattern(self, message: str, context: Optional[dict] = None):
        self._emit("PATTERN", message, context)

    # ================================
    # 4. Internal Emit
    # ================================

    def _emit(self, level: str, message: str, context: Optional[dict]):
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        ctx = f" | {context}" if context else ""
        print(f"[{level}][{self.name}][{ts}] {message}{ctx}")

# ================================
# TEACHING NOTE
# ================================
# Good logs teach you how the system thinks.
# If logs are confusing, the logic probably is too.

# ================================
# 5. Standalone Execution
# ================================

if __name__ == "__main__":
    log = Logger("SYSTEM")
    log.info("Logging framework initialized")

# ================================
# END OF FILE
# ================================
