"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""

from datetime import datetime
from typing import List

from execution.execution_engine import ExecutionEngine
from patterns.pattern_engine import PatternEngine
from portfolio.active_trade_registry import active_trade_registry
from risk.risk_engine import RiskEngine
from scanner.scanner import Scanner
from models.data_models import ExecutionResult, RiskDecision, TradeIntent, TradeRecord
from storage.storage_engine import StorageEngine
from strategy.strategy_runner import StrategyRunner


class CoreOrchestrator:
    def __init__(self):
        print("[INFO] Core Orchestrator initialised.")
        self.scanner = Scanner()
        self.pattern_engine = PatternEngine()
        self.strategy_runner = StrategyRunner()
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        self.storage_engine = StorageEngine()

    def run_once(self):
        """Run a single conceptual system cycle in teaching order."""
        print("[INFO] Starting orchestrator cycle (teaching-only).")
        self._auto_close_simulated_trades()

        print("[TEACH] >>> Scanner stage — gather candidates (conceptual).")
        scanner_results = self.scanner.run_scan_cycle()
        if not scanner_results:
            print("[SCAN] Scanner returned no candidates — placeholder outcome.")
        else:
            print(f"[SCAN] Scanner produced candidates: {scanner_results}")
        print("[TEACH] <<< Scanner stage complete — moving to pattern stage.")

        print("[TEACH] >>> Pattern stage — evaluate shapes/behaviors (conceptual).")
        pattern_results = self.pattern_engine.evaluate_patterns(scanner_results or [])
        if not pattern_results:
            print("[PATTERN] No patterns detected — placeholder outcome.")
        else:
            print(f"[PATTERN] Patterns evaluated: {pattern_results}")
        print("[TEACH] <<< Pattern stage complete — moving to strategy stage.")

        print("[TEACH] >>> Strategy stage — decide on trade ideas (conceptual).")
        strategy_output = self.strategy_runner.generate_trade_intent(pattern_results or [])
        if not strategy_output:
            print("[STRATEGY] No trade intents generated — placeholder outcome.")
        else:
            print(f"[STRATEGY] Trade intents generated: {strategy_output}")
        print("[TEACH] <<< Strategy stage complete — moving to risk stage.")

        print("[TEACH] >>> Risk stage — check sizing and limits (conceptual).")
        risk_output: List[RiskDecision] = []
        if not strategy_output:
            print("[RISK] No risk decision produced — placeholder outcome.")
        else:
            print(
                f"[TEACH] Risk engine will evaluate {len(strategy_output)} trade intents individually."
            )
            for trade_intent in strategy_output:
                print(
                    f"[TEACH] Evaluating risk for symbol: {trade_intent.symbol} "
                    f"(trader_type={trade_intent.trader_type})"
                )
                decision = self.risk_engine.evaluate_trade_intent(trade_intent)
                decision.trader_type = getattr(trade_intent, "trader_type", "MANUAL")
                decision.strategy_name = getattr(
                    trade_intent, "strategy_name", "UNKNOWN"
                )
                decision.direction = getattr(trade_intent, "direction", "UNKNOWN")
                risk_output.append(decision)
            if not risk_output:
                print("[RISK] No risk decision produced — placeholder outcome.")
            else:
                print(f"[RISK] Risk decision produced: {risk_output}")
        print("[TEACH] <<< Risk stage complete — moving to execution stage.")

        print("[TEACH] >>> Execution stage — send/prepare orders (conceptual).")
        execution_output: List[ExecutionResult] = []
        if not risk_output:
            print("[EXECUTION] No execution result — placeholder outcome.")
        else:
            print(f"[TEACH] Execution engine will handle {len(risk_output)} risk decisions individually.")
            for risk_decision in risk_output:
                print(
                    f"[TEACH] Routing execution for symbol: {risk_decision.symbol} "
                    f"(trader_type={risk_decision.trader_type})"
                )
                execution_output.append(self.execution_engine.execute_trade(risk_decision))
            if not execution_output:
                print("[EXECUTION] No execution results captured — placeholder outcome.")
            else:
                print(f"[EXECUTION] Execution results: {execution_output}")
        print("[TEACH] <<< Execution stage complete — moving to storage stage.")

        print("[TEACH] >>> Storage stage — record decisions/results (conceptual).")
        print("[TEACH] Creating TradeRecord to capture stage outputs for review.")
        trade_record = TradeRecord(
            scanner_output=scanner_results or [],
            pattern_output=pattern_results or [],
            strategy_output=strategy_output or [],
            risk_output=risk_output or [],
            execution_output=execution_output or [],
        )
        print("[TEACH] TradeRecord encapsulates the journey for teaching purposes.")
        storage_result = self.storage_engine.store_trade_record(trade_record)
        if storage_result is None:
            print("[STORAGE] No storage action taken — placeholder outcome.")
        else:
            print(f"[STORAGE] Storage result: {storage_result}")
        print("[TEACH] <<< Storage stage complete.")

        print(
            "[SUMMARY] "
            f"scanner={len(scanner_results or [])} | "
            f"patterns={len(pattern_results or [])} | "
            f"trade_intents={len(strategy_output or [])} | "
            f"risk_decisions={len(risk_output or [])} | "
            f"execution_results={len(execution_output or [])}"
        )

        print("[INFO] Orchestrator cycle complete (teaching-only).")

    def _auto_close_simulated_trades(self, max_age_seconds: int = 10) -> None:
        """
        Close any open ActiveTrades older than max_age_seconds using SIM rule.
        """

        now = datetime.utcnow()
        open_trades = active_trade_registry.get_active_trades()
        for trade in open_trades:
            age_seconds = (now - trade.entry_timestamp).total_seconds()
            if age_seconds >= max_age_seconds:
                print(
                    "[TEACH] Auto-closing trade_id="
                    f"{trade.trade_id} symbol={trade.symbol} age={age_seconds:.2f}s "
                    "via SIM_TIME_EXIT rule"
                )
                active_trade_registry.close_trade(trade.trade_id, "SIM_TIME_EXIT")
