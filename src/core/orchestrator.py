"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Set, Tuple

from brokers import IbkrBroker, SimBroker
from config.runtime_config import (
    EventReplayMode,
    RunMode,
    get_event_replay_mode,
    get_run_mode,
)
from config.system_config import get_current_market_session
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from core.faults import (
    RecoveryAction,
    classify_exception,
    decide_recovery_action,
    fault_to_payload,
)
from core.stop_controller import StopController, StopMode
from core.performance_registry import PerformanceRegistry
from core.replay_engine import ReplayEngine
from execution.execution_engine import ExecutionEngine
from execution.order_gateway import OrderGateway
from execution.trade_exit_engine import TradeExitEngine
from performance.strategy_performance import StrategyPerformanceTracker
from models.data_models import ExecutionResult, RiskDecision, TradeIntent, TradeRecord
from patterns.pattern_engine import PatternEngine
from risk.risk_engine import RiskEngine
from scanner.scanner import Scanner
from sim.clock import SimClock
from sim.price_feed import DeterministicPriceFeed
from signals.engine import SignalEngine
from signals.registry import build_default_signal_registry
from signals.signal_to_intent_adapter import SignalToIntentAdapter, SignalToIntentConfig
from signals.types import SignalContext, SignalDecision
from storage.storage_engine import StorageEngine
from strategy.strategy_runner import StrategyRunner
from strategy.exit_signal import ExitSignal
from events.event_invariants import check_invariants, EventInvariantError


class RuntimeSafetyError(RuntimeError):
    """Raised when a runtime safety gate is violated."""


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
        self.stop_controller = StopController()
        print("[BOOT] EventCollector initialised")
        self.replay_engine = ReplayEngine()
        self.performance_registry = PerformanceRegistry()
        self.trade_registry = ActiveTradeRegistry()
        self.strategy_perf_tracker = StrategyPerformanceTracker()
        self.scanner = Scanner()
        self.pattern_engine = PatternEngine()
        self.signal_registry = build_default_signal_registry()
        self.signal_engine = SignalEngine(
            registry=self.signal_registry,
            event_collector=self.event_collector,
        )
        self.signal_intent_adapter = SignalToIntentAdapter(
            config=SignalToIntentConfig(),
            event_collector=self.event_collector,
        )
        self.strategy_runner = StrategyRunner(event_collector=self.event_collector)
        self.risk_engine = RiskEngine(trade_registry=self.trade_registry)
        if self.run_mode == RunMode.SIM:
            broker = SimBroker(
                gateway=OrderGateway(),
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )
        else:
            broker = IbkrBroker()
        self.execution_engine = ExecutionEngine(
            broker=broker,
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            price_feed=self.price_feed,
        )
        self.trade_exit_engine = TradeExitEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
        )
        self.storage_engine = StorageEngine()
        self._halted = False
        self._degraded = False
        print(f"[BOOT] Event replay mode resolved — mode={self.replay_mode.value}")

    def replay_events(self, events):
        self.replay_engine.replay(events)

    def replay_cycle_events(self):
        print("[REPLAY] Initiating cycle-scoped replay")
        self.replay_events(self.event_collector.snapshot_cycle())

    def replay_all_events(self):
        print("[REPLAY] Initiating full-run replay")
        self.replay_events(self.event_collector.snapshot_all())

    def _stop_payload(self, mode: Optional[StopMode] = None) -> dict:
        resolved_mode = mode or self.stop_controller.stop_mode() or StopMode.GRACEFUL
        return {
            "mode": resolved_mode.value,
            "reason": self.stop_controller.stop_reason() or "No reason provided",
            "source": self.stop_controller.stop_source() or "Unknown",
            "run_mode": self.run_mode.value,
            "tick": self.sim_clock.now(),
        }

    def _request_stop(self, mode: StopMode, reason: str, source: str) -> StopMode:
        previous_mode = self.stop_controller.stop_mode()
        self.stop_controller.request_stop(mode, reason, source)
        resolved_mode = self.stop_controller.stop_mode() or mode
        self._halted = True
        if previous_mode is None:
            self.event_collector.emit(
                event_type="SHUTDOWN_REQUESTED",
                source="CoreOrchestrator",
                payload=self._stop_payload(resolved_mode),
                include_cycle=False,
            )
        if resolved_mode == StopMode.PANIC and (
            previous_mode is None or previous_mode == StopMode.GRACEFUL
        ):
            self.event_collector.emit(
                event_type="PANIC_STOP_TRIGGERED",
                source="CoreOrchestrator",
                payload=self._stop_payload(resolved_mode),
                include_cycle=False,
            )
        return resolved_mode

    def _stop_requested_at_boundary(self, stage_label: str) -> bool:
        if self.stop_controller.is_stop_requested():
            mode = self.stop_controller.stop_mode() or StopMode.GRACEFUL
            print(
                f"[STOP] Stop requested at stage boundary '{stage_label}' "
                f"— mode={mode.value}"
            )
            self._halted = True
            return True
        if self._halted:
            print(
                f"[STOP] Orchestrator halted prior to stage '{stage_label}' "
                "— exiting cycle safely."
            )
            return True
        return False

    def _handle_keyboard_interrupt(self):
        if not self.stop_controller.is_stop_requested():
            print("[SHUTDOWN] KeyboardInterrupt — requesting graceful stop.")
            self._request_stop(
                StopMode.GRACEFUL,
                reason="KeyboardInterrupt",
                source="Main",
            )
            return
        print("[SHUTDOWN] KeyboardInterrupt escalation — triggering panic stop.")
        self._request_stop(
            StopMode.PANIC,
            reason="KeyboardInterrupt (escalation)",
            source="Main",
        )

    def run_forever(
        self,
        cycle_sleep_seconds: Optional[int] = None,
        max_cycles: Optional[int] = None,
    ) -> None:
        """
        Continuous orchestrator loop with integrated stop handling.

        - Respects market session gates for LIVE mode.
        - Responds to KeyboardInterrupt with graceful then panic escalation.
        - Executes shutdown sequence when stop is requested.
        """

        from config.system_config import (
            ACTIVE_SESSIONS,
            CYCLE_SLEEP_SECONDS,
            get_current_market_session,
        )
        import time

        sleep_seconds = (
            CYCLE_SLEEP_SECONDS if cycle_sleep_seconds is None else cycle_sleep_seconds
        )
        cycles_run = 0
        performed_shutdown = False

        while True:
            try:
                if self.stop_controller.is_stop_requested():
                    self._shutdown(self.stop_controller.stop_mode() or StopMode.GRACEFUL)
                    performed_shutdown = True
                    break

                if max_cycles is not None and cycles_run >= max_cycles:
                    break

                print("[CYCLE] Starting orchestrator cycle.")
                current_session = get_current_market_session()
                print(f"[SESSION] Detected market session: {current_session}")
                if current_session in ACTIVE_SESSIONS:
                    print(
                        "[SESSION] System WOULD consider trading allowed in this session "
                        "(teaching-only)."
                    )
                else:
                    print(
                        "[SESSION] System WOULD treat market as closed (teaching-only)."
                    )
                if self.run_mode == RunMode.LIVE and current_session == "CLOSED":
                    print(
                        "[GATE] RUN_MODE is LIVE while session is CLOSED. "
                        "Skipping orchestrator.run_once() to maintain teaching-first safety."
                    )
                    print(
                        "[GATE] Teaching note: SIM/PAPER would still run for education, "
                        "but LIVE waits for an open session."
                    )
                else:
                    print(
                        "[SAFETY] RUN_MODE and session allow safe progression to orchestrator.run_once()."
                    )
                    should_continue = self.run_once()
                    cycles_run += 1
                    if should_continue is False:
                        if not self.stop_controller.is_stop_requested():
                            self._request_stop(
                                StopMode.GRACEFUL,
                                reason="Cycle requested halt",
                                source="CoreOrchestrator",
                            )
                        self._shutdown(self.stop_controller.stop_mode() or StopMode.GRACEFUL)
                        performed_shutdown = True
                        break

                print(f"[SLEEP] Sleeping for {sleep_seconds} seconds before next cycle.")
                time.sleep(sleep_seconds)
            except KeyboardInterrupt:
                self._handle_keyboard_interrupt()
                continue
        if not performed_shutdown:
            if not self.stop_controller.is_stop_requested():
                self._request_stop(
                    StopMode.GRACEFUL,
                    reason="Run loop complete",
                    source="CoreOrchestrator",
                )
            self._shutdown(self.stop_controller.stop_mode() or StopMode.GRACEFUL)

    def run_once(self) -> bool:
        """Run a single conceptual system cycle in teaching order."""
        if self._stop_requested_at_boundary("PRE_CYCLE"):
            return False
        try:
            return self._run_once_inner()
        except SystemExit:
            raise
        except Exception as exc:
            return self._handle_fault(exc)

    def _run_once_inner(self) -> bool:
        print("[INFO] Starting orchestrator cycle (teaching-only).")
        tick = self.sim_clock.tick()
        print(f"[CYCLE_CTX] tick={tick} run_mode={self.run_mode.value}")
        self.execution_engine.current_tick = tick
        self.event_collector.clear_cycle()
        event = self.event_collector.emit(
            event_type="CYCLE_START",
            source="Orchestrator",
            payload={"run_mode": self.run_mode}
        )
        print(event)
        self._evaluate_runtime_safety(
            cycle_stage="CYCLE_START",
            stage_exception=None,
        )
        if self._stop_requested_at_boundary("CYCLE_START"):
            return False

        print("[TEACH] >>> Scanner stage — gather candidates (conceptual).")
        try:
            scanner_results = self.scanner.run_scan_cycle()
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="SCANNER",
                stage_exception=exc,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="SCANNER",
            stage_exception=None,
            scanner_results=scanner_results,
        )
        if self._stop_requested_at_boundary("SCANNER"):
            return False
        event = self.event_collector.emit(
            event_type="SCAN_COMPLETE",
            source="Scanner",
            payload={"candidates": len(scanner_results or [])}
        )
        print(event)
        if not scanner_results:
            print("[SCAN] Scanner returned no candidates — placeholder outcome.")
        else:
            print(f"[SCAN] Scanner produced candidates: {scanner_results}")
        print("[TEACH] <<< Scanner stage complete — moving to pattern stage.")

        print("[TEACH] >>> Pattern stage — evaluate shapes/behaviors (conceptual).")
        try:
            pattern_results = self.pattern_engine.evaluate_patterns(scanner_results or [])
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="PATTERN",
                stage_exception=exc,
                scanner_results=scanner_results,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="PATTERN",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
        )
        if not pattern_results:
            print("[PATTERN] No patterns detected — placeholder outcome.")
        else:
            print(f"[PATTERN] Patterns evaluated: {pattern_results}")
        print("[TEACH] <<< Pattern stage complete — moving to strategy stage.")
        if self._stop_requested_at_boundary("PATTERN"):
            return False

        print("[TEACH] >>> Signals stage — evaluate momentum triggers (teaching).")
        current_session = get_current_market_session()
        signal_context = SignalContext(
            symbol="",
            tick=tick,
            run_mode=self.run_mode.value,
            session=current_session,
        )
        inputs_by_symbol = {}
        if scanner_results:
            def quantize_price(value: Decimal) -> Decimal:
                return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            for candidate in scanner_results:
                price = quantize_price(Decimal(str(candidate.price)))
                inputs_by_symbol[candidate.symbol] = {
                    "last_price": price,
                    "hod": quantize_price(price * Decimal("1.00")),
                    "pmh": quantize_price(price * Decimal("0.99")),
                    "vwap": quantize_price(price * Decimal("0.995")),
                    "orb_high": quantize_price(price * Decimal("1.01")),
                    "pullback_low": quantize_price(price * Decimal("0.97")),
                }

        signals_by_symbol = self.signal_engine.evaluate_all(
            signal_context,
            inputs_by_symbol,
        )
        for symbol, events in signals_by_symbol.items():
            signal_names = [
                event.signal_type.value
                for event in events
                if event.decision == SignalDecision.SIGNAL
            ]
            print(
                f"[SIGNALS] symbol={symbol} signals={len(signal_names)} "
                f"({', '.join(signal_names)})"
            )
        if not signals_by_symbol and scanner_results:
            for candidate in scanner_results:
                print(f"[SIGNALS] symbol={candidate.symbol} signals=0 ()")
        print("[TEACH] <<< Signals stage complete — moving to signal adapter stage.")

        print("[TEACH] >>> Signal adapter stage — map signals to trade intents (teaching).")
        signals = [
            event for events in signals_by_symbol.values() for event in events
        ]
        adapter_intents = self.signal_intent_adapter.convert(signals, tick=tick)
        print(
            f"[SIGNAL_ADAPTER] signals_in={len(signals)} intents_out={len(adapter_intents)}"
        )
        print("[TEACH] <<< Signal adapter stage complete — moving to strategy stage.")

        print("[TEACH] >>> Strategy stage — decide on trade ideas (conceptual).")
        try:
            strategy_intents = self.strategy_runner.generate_trade_intents(
                pattern_results or [],
                signals=signals,
            )
            strategy_intents = self.strategy_runner.run_from_intents(strategy_intents)
            merged_intents = self._merge_trade_intents(
                adapter_intents,
                strategy_intents,
            )
            print(
                "[INTENTS] merged total="
                f"{len(merged_intents)} "
                f"(adapter={len(adapter_intents)} strategy={len(strategy_intents)})"
            )
            strategy_output = merged_intents
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="STRATEGY",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="STRATEGY",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
        )
        if self._stop_requested_at_boundary("STRATEGY"):
            return False
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
            try:
                for trade_intent in strategy_output:
                    print(
                        f"[TEACH] Evaluating risk for symbol: {trade_intent.symbol} "
                        f"(trader_type={trade_intent.trader_type})"
                    )
                    decision = self.risk_engine.evaluate_trade_intent(trade_intent)
                    decision.trader_type = getattr(trade_intent, "trader_type", "MANUAL")
                    risk_output.append(decision)
            except Exception as exc:
                self._evaluate_runtime_safety(
                    cycle_stage="RISK",
                    stage_exception=exc,
                    scanner_results=scanner_results,
                    pattern_results=pattern_results,
                    strategy_output=strategy_output,
                )
                return False
            if not risk_output:
                print("[RISK] No risk decision produced — placeholder outcome.")
            else:
                print(f"[RISK] Risk decision produced: {risk_output}")
        self._evaluate_runtime_safety(
            cycle_stage="RISK",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
            risk_output=risk_output,
        )
        print("[TEACH] <<< Risk stage complete — moving to execution stage.")
        if self._stop_requested_at_boundary("RISK"):
            return False

        print("[TEACH] >>> Execution stage — send/prepare orders (conceptual).")
        execution_output: List[ExecutionResult] = []
        pending_results = self.execution_engine.process_pending_orders(tick)
        execution_output.extend(pending_results)
        if not risk_output:
            print("[EXECUTION] No execution result — placeholder outcome.")
        else:
            print(f"[TEACH] Execution engine will handle {len(risk_output)} risk decisions individually.")
            for risk_decision in risk_output:
                print(
                    f"[TEACH] Routing execution for symbol: {risk_decision.symbol} "
                    f"(trader_type={risk_decision.trader_type})"
                )
                try:
                    execution_output.append(self.execution_engine.execute_trade(risk_decision))
                except Exception as exc:
                    self._evaluate_runtime_safety(
                        cycle_stage="EXECUTION",
                        stage_exception=exc,
                        scanner_results=scanner_results,
                        pattern_results=pattern_results,
                        strategy_output=strategy_output,
                        risk_output=risk_output,
                    )
                    return False
            if not execution_output:
                print("[EXECUTION] No execution results captured — placeholder outcome.")
            else:
                print(f"[EXECUTION] Execution results: {execution_output}")
        self._evaluate_runtime_safety(
            cycle_stage="EXECUTION",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
            risk_output=risk_output,
            execution_output=execution_output,
        )
        print("[TEACH] <<< Execution stage complete — moving to strategy exit stage.")
        if self._stop_requested_at_boundary("EXECUTION"):
            return False

        print("[TEACH] >>> Strategy Exit stage — allow strategies to request exits (conceptual).")
        exit_signals: List[ExitSignal] = []
        try:
            active_trades_snapshot = self.trade_registry.snapshot()
            exit_signals = self.strategy_runner.generate_exit_signals(
                active_trades=active_trades_snapshot,
                current_tick=tick,
            )
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="EXIT_SIGNALS",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
                risk_output=risk_output,
                execution_output=execution_output,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="EXIT_SIGNALS",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
            risk_output=risk_output,
            execution_output=execution_output,
        )
        exit_signal_event = self.event_collector.emit(
            event_type="EXIT_SIGNALS_GENERATED",
            source="StrategyRunner",
            payload={"exit_signals": len(exit_signals or [])},
        )
        print(exit_signal_event)
        if not exit_signals:
            print("[EXIT] No strategy-driven exit requests this cycle.")
        else:
            print(f"[EXIT] Strategy exit requests generated: {exit_signals}")
        print("[TEACH] <<< Strategy Exit stage complete — moving to trade exit stage.")
        if self._stop_requested_at_boundary("EXIT_SIGNALS"):
            return False

        print("[TEACH] >>> Trade Exit stage — manage open trades explicitly.")
        try:
            exit_results, trade_outcomes = self.trade_exit_engine.evaluate_and_close_trades(
                run_mode=self.run_mode,
                tick=tick,
                exit_signals=exit_signals,
            )
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="TRADE_EXIT",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
                risk_output=risk_output,
                execution_output=execution_output,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="TRADE_EXIT",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
            risk_output=risk_output,
            execution_output=execution_output,
            exit_results=exit_results,
            trade_outcomes=trade_outcomes,
        )
        execution_complete_event = self.event_collector.emit(
            event_type="EXECUTION_COMPLETE",
            source="ExecutionEngine",
            payload={"results": len(execution_output or [])}
        )
        print(execution_complete_event)
        event = self.event_collector.emit(
            event_type="TRADE_EXIT_COMPLETE",
            source="TradeExitEngine",
            payload={"closed": len(exit_results or []), "outcomes": len(trade_outcomes or [])}
        )
        print(event)
        if not exit_results:
            print("[EXIT] No trades closed by TradeExitEngine this cycle.")
        else:
            print(f"[EXIT] TradeExitEngine closed trades: {exit_results}")
        if trade_outcomes:
            print(f"[EXIT] Realised trade outcomes: {trade_outcomes}")
        print("[TEACH] <<< Trade Exit stage complete — moving to storage stage.")
        if self._stop_requested_at_boundary("TRADE_EXIT"):
            return False

        closed_trade_events = [
            event
            for event in self.event_collector.snapshot_cycle()
            if event.event_type == "TRADE_CLOSED"
        ]

        self.performance_registry.record(closed_trade_events)
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
        perf_snapshot_event = self.event_collector.emit(
            event_type="PERF_SNAPSHOT",
            source="PerformanceRegistry",
            payload=asdict(performance_snapshot),
        )
        print(perf_snapshot_event)
        for event in closed_trade_events:
            self.strategy_perf_tracker.record_trade_close(event.payload or {})
        strategy_snapshots = self.strategy_perf_tracker.snapshot()
        strategy_perf_payload = [
            {
                "strategy_name": snapshot.strategy_name,
                "total_trades": snapshot.total_trades,
                "wins": snapshot.wins,
                "losses": snapshot.losses,
                "flats": snapshot.flats,
                "gross_pnl": snapshot.gross_pnl,
                "win_rate": snapshot.win_rate,
            }
            for snapshot in strategy_snapshots
        ]
        strategy_perf_event = self.event_collector.emit(
            event_type="STRATEGY_PERF_SNAPSHOT",
            source="CoreOrchestrator",
            payload={"strategies": strategy_perf_payload},
        )
        print(strategy_perf_event)

        print("[TEACH] >>> Storage stage — record decisions/results (conceptual).")
        print("[TEACH] Creating TradeRecord to capture stage outputs for review.")
        try:
            trade_record = TradeRecord(
                scanner_output=scanner_results or [],
                pattern_output=pattern_results or [],
                strategy_output=strategy_output or [],
                risk_output=risk_output or [],
                execution_output=execution_output or [],
                trade_outcomes=trade_outcomes or [],
                performance_snapshot=performance_snapshot,
            )
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="STORAGE",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
                risk_output=risk_output,
                execution_output=execution_output,
                exit_results=exit_results,
                trade_outcomes=trade_outcomes,
            )
            return False
        print("[TEACH] TradeRecord encapsulates the journey for teaching purposes.")
        try:
            storage_result = self.storage_engine.store_trade_record(trade_record)
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="STORAGE",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
                risk_output=risk_output,
                execution_output=execution_output,
                exit_results=exit_results,
                trade_outcomes=trade_outcomes,
                trade_record=trade_record,
            )
            return False
        if storage_result is None:
            print("[STORAGE] No storage action taken — placeholder outcome.")
        else:
            print(f"[STORAGE] Storage result: {storage_result}")
        self._evaluate_runtime_safety(
            cycle_stage="STORAGE",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
            risk_output=risk_output,
            execution_output=execution_output,
            exit_results=exit_results,
            trade_outcomes=trade_outcomes,
            trade_record=trade_record,
        )
        print("[TEACH] <<< Storage stage complete.")
        if self._stop_requested_at_boundary("STORAGE"):
            return False

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
        pnl_by_trader_type_summary = (
            " | ".join(pnl_by_trader_type_parts) if pnl_by_trader_type_parts else "N/A"
        )
        print("[PNL_BY_STRATEGY]")
        if not strategy_snapshots:
            print("N/A")
        else:
            for snapshot in strategy_snapshots:
                print(
                    f"{snapshot.strategy_name}: "
                    f"trades={snapshot.total_trades} "
                    f"wins={snapshot.wins} "
                    f"losses={snapshot.losses} "
                    f"flats={snapshot.flats} "
                    f"win_rate={snapshot.win_rate:.2f} "
                    f"gross_pnl={snapshot.gross_pnl:.2f}"
                )
        print(f"[PNL_BY_TRADER_TYPE] {pnl_by_trader_type_summary}")
        try:
            check_invariants(all_snapshot)
            print("[INVARIANTS] OK")
        except EventInvariantError as exc:
            print(f"[INVARIANTS] FAILED: {exc}")
            self._evaluate_runtime_safety(
                cycle_stage="INVARIANTS",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
                risk_output=risk_output,
                execution_output=execution_output,
                exit_results=exit_results,
                trade_outcomes=trade_outcomes,
                trade_record=trade_record,
            )
            return False
        print(
            f"[REPLAY] Replay selection — mode={self.replay_mode.value} "
            f"run_mode={run_mode_value}"
        )
        if self.run_mode == RunMode.LIVE:
            print("[REPLAY] Replay is locked down in LIVE mode — skipping replay")
            return True
        events_for_replay = self.event_collector.get_events_for_replay(
            self.replay_mode
        )
        if (
            self.replay_mode == EventReplayMode.CYCLE
            and self.event_collector.cycle_count("TRADE_CLOSED") > 0
            and self.event_collector.cycle_count("TRADE_OPENED") == 0
        ):
            print(
                "[REPLAY] Cycle replay missing TRADE_OPENED context — "
                "falling back to run-scope events for invariant safety."
            )
            events_for_replay = all_snapshot
        if not events_for_replay:
            print("[REPLAY] No events selected for replay")
            return True
        self.replay_events(events_for_replay)
        return True

    def _merge_trade_intents(
        self,
        adapter_intents: List[TradeIntent],
        strategy_intents: List[TradeIntent],
    ) -> List[TradeIntent]:
        merged: Dict[Tuple[str, str, str], TradeIntent] = {}
        sources: Dict[Tuple[str, str, str], str] = {}

        def consider(intent: TradeIntent, source: str) -> None:
            key = (intent.symbol, intent.direction, intent.trader_type)
            current = merged.get(key)
            if current is None:
                merged[key] = intent
                sources[key] = source
                return
            if intent.confidence > current.confidence:
                merged[key] = intent
                sources[key] = source
                return
            if (
                intent.confidence == current.confidence
                and source == "adapter"
                and sources.get(key) != "adapter"
            ):
                merged[key] = intent
                sources[key] = source

        for intent in adapter_intents:
            consider(intent, "adapter")
        for intent in strategy_intents:
            consider(intent, "strategy")

        return [merged[key] for key in sorted(merged.keys())]

    def _handle_fault(self, exc: Exception) -> bool:
        fault = classify_exception(exc)
        fault_event = self.event_collector.emit(
            event_type="FAULT_DETECTED",
            source="Orchestrator",
            payload=fault_to_payload(fault, self.run_mode),
        )
        print(fault_event)
        action = decide_recovery_action(fault, self.run_mode)
        action_event = self.event_collector.emit(
            event_type="FAULT_ACTION_TAKEN",
            source="Orchestrator",
            payload=fault_to_payload(fault, self.run_mode, action),
        )
        print(action_event)

        if action == RecoveryAction.IGNORE:
            print("[FAULT] Action=IGNORE — continuing cycle execution.")
            return True
        if action == RecoveryAction.RETRY:
            print("[FAULT] Action=RETRY — bounded retry not implemented; aborting cycle.")
            return False
        if action == RecoveryAction.SKIP_STAGE:
            print("[FAULT] Action=SKIP_STAGE — skipping stage not implemented; aborting cycle.")
            return False
        if action == RecoveryAction.SKIP_CYCLE:
            print("[FAULT] Action=SKIP_CYCLE — skipping the remainder of this cycle.")
            return True
        if action == RecoveryAction.DEGRADE_MODE:
            print("[FAULT] Action=DEGRADE_MODE — entering degraded mode but continuing.")
            self._degraded = True
            return True
        if action == RecoveryAction.ABORT_CYCLE:
            print("[FAULT] Action=ABORT_CYCLE — aborting current cycle safely.")
            return False
        if action == RecoveryAction.HALT_SYSTEM:
            print("[FAULT] Action=HALT_SYSTEM — halting orchestrator safely.")
            mode = StopMode.PANIC if self.run_mode == RunMode.LIVE else StopMode.GRACEFUL
            self._request_stop(
                mode,
                reason=f"Fault: {fault.message}",
                source="FaultRecovery",
            )
            return False
        return False

    def _shutdown(self, mode: StopMode) -> None:
        """
        Structured shutdown sequence with hook isolation.

        GRACEFUL mode executes all hooks in order. PANIC mode skips
        non-essential steps to exit quickly while still emitting events.
        """

        resolved_mode = mode or StopMode.GRACEFUL
        print(f"[SHUTDOWN] Beginning {resolved_mode.value} shutdown sequence.")
        start_payload = self._stop_payload(resolved_mode)
        self.event_collector.emit(
            event_type="SHUTDOWN_STARTED",
            source="CoreOrchestrator",
            payload=start_payload,
            include_cycle=False,
        )
        if resolved_mode == StopMode.PANIC:
            print("[SHUTDOWN] Panic stop — running minimal hooks.")
            try:
                self.execution_engine.shutdown()
            except Exception as exc:
                fault = classify_exception(exc)
                hook_payload = {
                    **self._stop_payload(resolved_mode),
                    "hook": "execution_engine.shutdown",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "fault_category": fault.category.value,
                    "fault_severity": fault.severity.value,
                }
                self.event_collector.emit(
                    event_type="SHUTDOWN_HOOK_FAILED",
                    source="CoreOrchestrator",
                    payload=hook_payload,
                    include_cycle=False,
                )
            complete_payload = self._stop_payload(resolved_mode)
            self.event_collector.emit(
                event_type="SHUTDOWN_COMPLETE",
                source="CoreOrchestrator",
                payload=complete_payload,
                include_cycle=False,
            )
            return

        hooks = [
            ("execution_engine.shutdown", self.execution_engine.shutdown),
            ("trade_exit_engine.shutdown", self.trade_exit_engine.shutdown),
            ("storage_engine.shutdown", self.storage_engine.shutdown),
            ("event_collector.flush_summary", self.event_collector.flush_summary),
            ("active_trade_registry.verify_empty", self.trade_registry.verify_empty),
        ]

        for hook_name, hook_fn in hooks:
            try:
                result = hook_fn()
                if hook_name == "active_trade_registry.verify_empty" and result is False:
                    self.event_collector.emit(
                        event_type="SHUTDOWN_HOOK_FAILED",
                        source="CoreOrchestrator",
                        payload={
                            **self._stop_payload(resolved_mode),
                            "hook": hook_name,
                            "exception_type": "RegistryNotEmpty",
                            "exception_message": "Active trades remain during shutdown",
                            "fault_category": "STATE",
                            "fault_severity": "CRITICAL",
                        },
                        include_cycle=False,
                    )
            except Exception as exc:
                fault = classify_exception(exc)
                hook_payload = {
                    **self._stop_payload(resolved_mode),
                    "hook": hook_name,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "fault_category": fault.category.value,
                    "fault_severity": fault.severity.value,
                }
                self.event_collector.emit(
                    event_type="SHUTDOWN_HOOK_FAILED",
                    source="CoreOrchestrator",
                    payload=hook_payload,
                    include_cycle=False,
                )
                continue

        complete_payload = self._stop_payload(resolved_mode)
        self.event_collector.emit(
            event_type="SHUTDOWN_COMPLETE",
            source="CoreOrchestrator",
            payload=complete_payload,
            include_cycle=False,
        )

    def _evaluate_runtime_safety(
        self,
        cycle_stage: Optional[str],
        stage_exception: Optional[BaseException] = None,
        scanner_results: Optional[list] = None,
        pattern_results: Optional[list] = None,
        strategy_output: Optional[list] = None,
        risk_output: Optional[list] = None,
        execution_output: Optional[list] = None,
        exit_results: Optional[list] = None,
        trade_outcomes: Optional[list] = None,
        trade_record: Optional[TradeRecord] = None,
    ) -> None:
        """
        Enforce runtime safety gates.

        In LIVE mode, any violation halts the system immediately.
        In SIM/PAPER, violations raise an exception for visibility.
        """

        if self.stop_controller.is_stop_requested() or self._halted:
            print("[SAFETY] Orchestrator already halted — ignoring subsequent stages.")
            return

        violations: List[str] = []
        duplicate_keys: Set[Tuple[str, str]] = set()
        known_stages = {
            "CYCLE_START",
            "SCANNER",
            "PATTERN",
            "STRATEGY",
            "RISK",
            "EXECUTION",
            "EXIT_SIGNALS",
            "TRADE_EXIT",
            "STORAGE",
            "INVARIANTS",
        }
        stage_label = cycle_stage or "UNKNOWN"

        if self.run_mode == RunMode.LIVE and self.replay_mode != EventReplayMode.OFF:
            violations.append("Replay requested while in LIVE mode")
        if self.run_mode == RunMode.LIVE and isinstance(self.sim_clock, SimClock):
            violations.append("Deterministic SimClock detected in LIVE mode")
        if self.run_mode == RunMode.LIVE and isinstance(
            self.price_feed, DeterministicPriceFeed
        ):
            violations.append("Deterministic price feed detected in LIVE mode")

        active_trades = self.trade_registry.snapshot()
        if len(active_trades) < 0:
            violations.append("Active trade count is negative (undefined state)")
        seen_keys: Set[Tuple[str, str]] = set()
        for trade in active_trades:
            key = (trade.symbol, trade.trader_type)
            if key in seen_keys:
                duplicate_keys.add(key)
            seen_keys.add(key)
        if duplicate_keys:
            duplicates_display = ", ".join(sorted(f"{s}:{t}" for s, t in duplicate_keys))
            violations.append(
                f"Duplicate active trade keys detected: {duplicates_display}"
            )

        if cycle_stage not in known_stages:
            violations.append("Orchestrator entered an undefined stage")

        if stage_exception is not None:
            violations.append(
                f"Unhandled exception in stage {stage_label}: {stage_exception}"
            )

        if not violations:
            return

        payload = {
            "stage": stage_label,
            "run_mode": self.run_mode.value,
            "replay_mode": getattr(self.replay_mode, "value", str(self.replay_mode)),
            "violations": violations,
        }
        if duplicate_keys:
            payload["duplicate_keys"] = list(duplicate_keys)
        if stage_exception is not None:
            payload["exception_type"] = type(stage_exception).__name__
            payload["exception_message"] = str(stage_exception)

        print(f"[SAFETY] Violations detected at stage={stage_label}: {violations}")
        violation_event = self.event_collector.emit(
            event_type="RUNTIME_SAFETY_VIOLATION",
            source="CoreOrchestrator",
            payload=payload,
        )
        print(violation_event)

        if self.run_mode == RunMode.LIVE:
            print("[SAFETY] LIVE mode violation — entering deterministic safe halt.")
            self._request_stop(
                StopMode.PANIC,
                reason="Runtime safety violation",
                source="RuntimeSafety",
            )
            return

        raise RuntimeSafetyError("; ".join(violations))
