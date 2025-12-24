# File: minimal_end_to_end_cycle_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Standalone end-to-end cycle runner (dry-run)

"""
MINIMAL RUNNABLE END-TO-END CYCLE (DRY-RUN)
------------------------------------------

GLOBAL CONTEXT
--------------
This script is the **first runnable integration** of the trading system.

It validates:
- wiring
- execution order
- logging
- storage call path

It does NOT:
- connect to IBKR
- fetch real market data
- place real orders

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_25_OUTCOME_MINIMAL_RUNNABLE_CYCLE.md

STANDALONE GUARANTEE
-------------------
Run this file directly to verify your environment.

TRADING MODE
------------
Dry-run only.
"""

# ================================
# 1. Imports
# ================================

from logging_framework_v01 import Logger

from scanner_engine_v01 import ScannerEngine
from pattern_engine_v01 import PatternEngine
from ross_momentum_runner_v01 import RossMomentumRunner
from risk_engine_v01 import RiskEngine
from execution_engine_v01 import ExecutionEngine
from storage_engine_v01 import StorageEngine

# ================================
# 2. Runner
# ================================

class MinimalEndToEndRunner:
    """
    MinimalEndToEndRunner
    ---------------------
    Runs a single dry-run cycle.
    """

    def __init__(self):
        self.log = Logger("RUNNER")
        self.scanner = ScannerEngine()
        self.patterns = PatternEngine(enabled_patterns=[])
        self.strategy = RossMomentumRunner()
        self.risk = RiskEngine()
        self.execution = ExecutionEngine()
        self.storage = StorageEngine()

    def run_once(self):
        """Run one full cycle."""
        self.log.info("Starting dry-run end-to-end cycle")

        scan = self.scanner.run_scan()
        pat = self.patterns.evaluate({})
        intent = self.strategy.evaluate(scan, pat)
        decision = self.risk.evaluate_trade(intent, account_state={})

        execution_result = None
        if decision.get("decision") == "ALLOW":
            execution_result = self.execution.submit_order(intent)

        self.storage.store_trade_attempt({
            "trade_intent": intent,
            "risk": decision,
            "execution": execution_result,
        })

        self.log.info("Dry-run cycle completed")

# ================================
# 3. Standalone Execution
# ================================

if __name__ == "__main__":
    runner = MinimalEndToEndRunner()
    runner.run_once()

# ================================
# END OF FILE
# ================================
