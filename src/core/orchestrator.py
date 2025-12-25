"""
File: orchestrator.py
Phase: PHASE 3 — Skeleton System
Purpose:
Central orchestrator that wires all modules together.
In Phase 3, this only demonstrates system flow with logs.
NO trading logic is implemented.
"""

from typing import List, Optional

from execution.execution_engine import ExecutionEngine
from models.data_models import TradeRecord
from patterns.pattern_engine import PatternEngine
from risk.risk_engine import RiskEngine
from scanner.scanner import Scanner
from storage.storage_engine import StorageEngine
from strategy.strategy_runner import StrategyRunner


class CoreOrchestrator:
    def __init__(self):
        print("[BOOT] Core Orchestrator initialised — wiring skeleton modules")
        self.session: Optional[str] = None
        self.scanner = Scanner()
        self.pattern_engine = PatternEngine()
        self.strategy_runner = StrategyRunner()
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        self.storage_engine = StorageEngine()

    def run_once(self):
        print("[INFO] Starting orchestrator cycle (Phase 3 skeleton)")
        if self.session is None:
            print("[INFO] Session context unavailable in skeleton — using None placeholder")

        scanner_results = self.scanner.run_scan_cycle()
        if not scanner_results:
            print("[SCAN] No scanner results returned — continuing with empty list")

        pattern_results = self.pattern_engine.evaluate_patterns(scanner_results if isinstance(scanner_results, list) else [])
        if not pattern_results:
            print("[PATTERN] No pattern results generated — strategy runner will see empty list")

        trade_intents = self.strategy_runner.generate_trade_intent(pattern_results if isinstance(pattern_results, list) else [])
        trade_intent_list: List = trade_intents if isinstance(trade_intents, list) else ([trade_intents] if trade_intents is not None else [])
        if not trade_intent_list:
            print("[STRATEGY] No trade intents generated — skipping risk evaluation loop")

        risk_decisions = []
        if not trade_intent_list:
            print("[RISK] No trade intents available — skipping risk evaluation")
        else:
            for trade_intent in trade_intent_list:
                if trade_intent is None:
                    print("[RISK] Trade intent is None — cannot evaluate risk in skeleton flow")
                    continue
                risk_decision = self.risk_engine.evaluate_trade_intent(trade_intent)
                risk_decisions.append(risk_decision)

        execution_results = []
        if not risk_decisions:
            print("[EXECUTION] No risk decisions to execute — skipping execution step")
        else:
            for risk_decision in risk_decisions:
                if risk_decision is None:
                    print("[EXECUTION] Risk decision missing — cannot execute trade in skeleton flow")
                    continue
                execution_result = self.execution_engine.execute_trade(risk_decision)
                if execution_result is None:
                    print("[EXECUTION] Execution returned None — no broker interaction in skeleton")
                else:
                    execution_results.append(execution_result)

        trade_record = TradeRecord(
            scanner_snapshots=scanner_results if isinstance(scanner_results, list) else [],
            pattern_results=pattern_results if isinstance(pattern_results, list) else [],
            trade_intent=trade_intent_list[0] if trade_intent_list else None,
            risk_decision=risk_decisions[0] if risk_decisions else None,
            execution_results=execution_results,
        )
        if trade_record.trade_intent is None:
            print("[STORAGE] TradeRecord built without trade intent — skeleton flow only")
        if not trade_record.pattern_results:
            print("[STORAGE] TradeRecord missing pattern results — no detections in skeleton cycle")

        stored = self.storage_engine.store_trade_record(trade_record)
        if stored:
            print("[STORAGE] TradeRecord storage acknowledged (skeleton placeholder)")
        else:
            print("[WARNING] TradeRecord storage reported failure — skeleton state")

        print("[INFO] Orchestrator cycle complete")

