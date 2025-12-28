"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""
from dataclasses import asdict
from typing import List

from config.runtime_config import RunMode, get_run_mode
from config.system_config import EventReplayMode, get_event_replay_mode
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from core.events import SystemEvent
from core.performance_registry import PerformanceRegistry
from core.replay_engine import ReplayEngine
from execution.execution_engine import ExecutionEngine
from execution.trade_exit_engine import TradeExitEngine
from models.data_models import ExecutionResult, RiskDecision, TradeIntent, TradeRecord
from patterns.pattern_engine import PatternEngine
from risk.risk_engine import RiskEngine
from scanner.scanner import Scanner
from sim.clock import SimClock
from sim.price_feed import DeterministicPriceFeed
from storage.storage_engine import StorageEngine
from strategy.strategy_runner import StrategyRunner


class CoreOrchestrator:
    def __init__(self):
        print("[INFO] Core Orchestrator initialised.")
        self.run_mode = get_run_mode()
        self.replay_mode = get_event_replay_mode(self.run_mode)
        if self.run_mode == RunMode.LIVE and self.replay_mode != EventReplayMode.OFF:
            print(
                "[SAFETY] Replay request detected in LIVE. Forcing EVENT_REPLAY_MODE=OFF."
            )
            self.replay_mode = EventReplayMode.OFF
        self.sim_clock = SimClock()
        self.price_feed = DeterministicPriceFeed()
        self.event_collector = EventCollector()
        print("[BOOT] EventCollector initialised")
        self.replay_engine = ReplayEngine()
        self.performance_registry = PerformanceRegistry()
        self.trade_registry = ActiveTradeRegistry()
        self.scanner = Scanner()
        self.pattern_engine = PatternEngine()
        self.strategy_runner = StrategyRunner()
        self.risk_engine = RiskEngine(trade_registry=self.trade_registry)
        self.execution_engine = ExecutionEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            price_feed=self.price_feed,
        )
        self.trade_exit_engine = TradeExitEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
        )
        self.storage_engine = StorageEngine()
        print(f"[BOOT] Event replay mode resolved — mode={self.replay_mode.value}")

    def replay_events(self, events):
        self.replay_engine.replay(events)

    def replay_cycle_events(self):
        print("[REPLAY] Initiating cycle-scoped replay")
        self.replay_events(self.event_collector.snapshot_cycle())

    def replay_all_events(self):
        print("[REPLAY] Initiating full-run replay")
        self.replay_events(self.event_collector.snapshot_all())

    def run_once(self):
        """Run a single conceptual system cycle in teaching order."""
        print("[INFO] Starting orchestrator cycle (teaching-only).")
        tick = self.sim_clock.tick()
        print(f"[CYCLE_CTX] tick={tick} run_mode={self.run_mode.value}")
        self.execution_engine.current_tick = tick
        self.event_collector.clear_cycle()
        event = SystemEvent(
            event_type="CYCLE_START",
            source="Orchestrator",
            payload={"run_mode": self.run_mode}
        )
        print(event)
        self.event_collector.record(event)

        print("[TEACH] >>> Scanner stage — gather candidates (conceptual).")
        scanner_results = self.scanner.run_scan_cycle()
        event = SystemEvent(
            event_type="SCAN_COMPLETE",
            source="Scanner",
            payload={"candidates": len(scanner_results or [])}
        )
        print(event)
        self.event_collector.record(event)
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
        event = SystemEvent(
            event_type="STRATEGY_COMPLETE",
            source="StrategyRunner",
            payload={"trade_intents": len(strategy_output or [])}
        )
        print(event)
        self.event_collector.record(event)
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
        event = SystemEvent(
            event_type="EXECUTION_COMPLETE",
            source="ExecutionEngine",
            payload={"results": len(execution_output or [])}
        )
        print(event)
        self.event_collector.record(event)
        print("[TEACH] <<< Execution stage complete — moving to storage stage.")

        print("[TEACH] >>> Trade Exit stage — manage open trades explicitly.")
        exit_results, trade_outcomes = self.trade_exit_engine.evaluate_and_close_trades(
            run_mode=self.run_mode,
            tick=tick,
        )
        event = SystemEvent(
            event_type="TRADE_EXIT_COMPLETE",
            source="TradeExitEngine",
            payload={"closed": len(exit_results or []), "outcomes": len(trade_outcomes or [])}
        )
        print(event)
        self.event_collector.record(event)
        if not exit_results:
            print("[EXIT] No trades closed by TradeExitEngine this cycle.")
        else:
            print(f"[EXIT] TradeExitEngine closed trades: {exit_results}")
        if trade_outcomes:
            print(f"[EXIT] Realised trade outcomes: {trade_outcomes}")
        print("[TEACH] <<< Trade Exit stage complete — moving to storage stage.")

        self.performance_registry.record(trade_outcomes or [])
        performance_snapshot = self.performance_registry.snapshot()
        print(
            "[PERF] "
            f"total={performance_snapshot.total_trades} "
            f"wins={performance_snapshot.wins} "
            f"losses={performance_snapshot.losses} "
            f"flats={performance_snapshot.flats} "
            f"win_rate={performance_snapshot.win_rate:.2f} "
            f"gross_pnl={performance_snapshot.gross_pnl:.2f} "
            f"avg_pnl={performance_snapshot.avg_pnl_per_trade:.2f}"
        )
        for strategy_name, bucket in sorted(performance_snapshot.by_strategy.items()):
            print(
                "[PERF] "
                f"strategy={strategy_name} "
                f"gross_pnl={bucket.get('gross_pnl', 0.0):.2f} "
                f"total_trades={bucket.get('total_trades', 0)}"
            )
        perf_snapshot_event = SystemEvent(
            event_type="PERF_SNAPSHOT",
            source="PerformanceRegistry",
            payload=asdict(performance_snapshot),
        )
        print(perf_snapshot_event)
        self.event_collector.record(perf_snapshot_event)

        print("[TEACH] >>> Storage stage — record decisions/results (conceptual).")
        print("[TEACH] Creating TradeRecord to capture stage outputs for review.")
        trade_record = TradeRecord(
            scanner_output=scanner_results or [],
            pattern_output=pattern_results or [],
            strategy_output=strategy_output or [],
            risk_output=risk_output or [],
            execution_output=execution_output or [],
            trade_outcomes=trade_outcomes or [],
            performance_snapshot=performance_snapshot,
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
        cycle_snapshot = self.event_collector.snapshot_cycle()
        all_snapshot = self.event_collector.snapshot_all()
        cycle_event_count = len(cycle_snapshot)
        all_event_count = len(all_snapshot)
        print(
            f"[EVENT_SUMMARY] Cycle produced {cycle_event_count} event(s) (cycle scope)"
        )
        print(
            f"[EVENT_SUMMARY] Run has {all_event_count} total event(s) (all cycles)"
        )
        print(
            f"[EVENT_SNAPSHOT] Captured "
            f"{len(cycle_snapshot)} events for replay"
        )
        for event in cycle_snapshot:
            print(
                f"[EVENT_SUMMARY] {event.timestamp} | {event.event_type} | {event.source}"
        )
        run_mode_value = self.run_mode.value
        opened_count = self.event_collector.cycle_count("TRADE_OPENED")
        closed_count = self.event_collector.cycle_count("TRADE_CLOSED")
        realised_pnl = f"{performance_snapshot.gross_pnl:.2f}"
        pnl_by_strategy = performance_snapshot.by_strategy
        pnl_by_trader_type = performance_snapshot.by_trader_type
        print(
            "[CYCLE_SUMMARY] "
            f"opened={opened_count} "
            f"closed={closed_count} "
            f"realised_pnl={realised_pnl} "
            f"run_mode={run_mode_value} "
            f"tick={tick}"
        )
        pnl_by_trader_type_parts = [
            f"{trader_type}={bucket.get('gross_pnl', 0.0):.2f}"
            for trader_type, bucket in sorted(
                pnl_by_trader_type.items(), key=lambda item: item[0]
            )
        ]
        pnl_by_strategy_parts = [
            f"{strategy_name}={bucket.get('gross_pnl', 0.0):.2f}"
            for strategy_name, bucket in sorted(
                pnl_by_strategy.items(), key=lambda item: item[0]
            )
        ]
        pnl_by_trader_type_summary = (
            " | ".join(pnl_by_trader_type_parts) if pnl_by_trader_type_parts else "N/A"
        )
        pnl_by_strategy_summary = (
            " | ".join(pnl_by_strategy_parts) if pnl_by_strategy_parts else "N/A"
        )
        print(f"[PNL_BY_STRATEGY] {pnl_by_strategy_summary}")
        print(f"[PNL_BY_TRADER_TYPE] {pnl_by_trader_type_summary}")
        print(
            f"[REPLAY] Replay selection — mode={self.replay_mode.value} "
            f"run_mode={run_mode_value}"
        )
        if self.run_mode == RunMode.LIVE:
            print("[REPLAY] Replay is locked down in LIVE mode — skipping replay")
            return
        events_for_replay = self.event_collector.get_events_for_replay(
            self.replay_mode
        )
        if not events_for_replay:
            print("[REPLAY] No events selected for replay")
            return
        self.replay_events(events_for_replay)
