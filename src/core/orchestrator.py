"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from typing import Dict, List, Optional, Set, Tuple

from src.brokers import IbkrLiveBroker, SimBroker
from src.config.config_resolver import emit_config_event, get_config
from src.config.runtime_config import (
    EventReplayMode,
    RunMode,
    get_daily_loss_hard_limit,
    get_daily_loss_warning_limit,
    get_live_micro_ack,
    get_live_micro_1_share_only,
)
from src.config.system_config import get_current_market_session
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.faults import (
    RecoveryAction,
    classify_exception,
    decide_recovery_action,
    fault_to_payload,
)
from src.core.stop_controller import StopController, StopMode
from src.core.performance_registry import PerformanceRegistry
from src.core.replay_engine import ReplayEngine
from src.execution.execution_engine import ExecutionEngine
from src.execution.order_gateway import OrderGateway
from src.execution.trade_exit_engine import TradeExitEngine
from src.ibkr.market_data_client import MarketDataClient
from src.learning.scheduler import LearningScheduler
from src.market_data.market_data_hub import MarketDataHub
from src.market_data.market_data_price_feed import MarketDataPriceFeed
from src.performance.strategy_performance import StrategyPerformanceTracker
from src.models.data_models import ExecutionResult, RiskDecision, TradeIntent, TradeRecord
from src.patterns.pattern_engine import PatternEngine
from src.risk.risk_engine import RiskEngine
from src.core.intent import build_execution_intent
from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_live_readonly import LiveReadOnlyScanner
from src.scanner.scanner import Scanner
from src.scanner.scanner_contract import ScannerRequest, scanner_request_from_policy
from src.scanner.scanner_runner import run_scanner_cycle
from src.sim.clock import SimClock, WallClock
from src.sim.price_feed import DeterministicPriceFeed
from src.signals.signal_engine_v1 import SignalEngineV1
from src.storage.storage_engine import StorageEngine
from src.strategy.strategy_runner import StrategyRunner
from src.strategy.exit_signal import ExitSignal
from src.events.event_invariants import check_invariants, EventInvariantError
from src.strategies.ross_momentum.strategy_context_schema import (
    StrategyContext,
    SymbolContext,
    SymbolIndicators,
    SymbolMarketData,
)
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    UniverseSource,
    stock_selection_policy_for_session_phase,
)
from src.utils.time_utils import market_session_phase, to_ny_time, to_uk_time
from src.regime.layer import RegimeLayer


class RuntimeSafetyError(RuntimeError):
    """Raised when a runtime safety gate is violated."""


class CoreOrchestrator:
    def __init__(self):
        print("[INFO] Core Orchestrator initialised.")
        self.run_mode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        self.execution_enabled = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        self.ibkr_api_write_allowed = bool(get_config("IBKR_API_WRITE_ALLOWED"))
        self.replay_mode = EventReplayMode(get_config("EVENT_REPLAY_MODE_EFFECTIVE"))
        if (
            self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}
            and self.replay_mode != EventReplayMode.OFF
        ):
            print(
                "[SAFETY] Replay request detected in LIVE/LIVE_READ_ONLY/LIVE_MICRO. "
                "Forcing EVENT_REPLAY_MODE=OFF."
            )
            self.replay_mode = EventReplayMode.OFF
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[SAFETY] ORDER ROUTING: BLOCKED")
        if self.run_mode == RunMode.LIVE_MICRO:
            print("[SAFETY] LIVE MICRO-EXECUTION MODE ACTIVE")
            print("[SAFETY] 1-SHARE LIMIT ENFORCED")
        if self.run_mode == RunMode.PAPER:
            print("[SAFETY] PAPER-EXECUTION MODE ACTIVE")
            print("[SAFETY] 1-SHARE LIMIT ENFORCED")
        if self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO, RunMode.PAPER}:
            self.sim_clock = WallClock()
        else:
            self.sim_clock = SimClock()
        self.event_collector = EventCollector()
        emit_config_event(self.event_collector)
        self.stop_controller = StopController()
        print("[BOOT] EventCollector initialised")
        self.replay_engine = ReplayEngine()
        self.performance_registry = PerformanceRegistry()
        self.trade_registry = ActiveTradeRegistry()
        self.strategy_perf_tracker = StrategyPerformanceTracker()
        self.market_data_hub = None
        if self.run_mode == RunMode.LIVE_READ_ONLY:
            from src.brokers import IbkrBroker

            if IbkrBroker is None:
                print(
                    "[MARKET_DATA][WARN] IbkrBroker unavailable; "
                    "falling back to deterministic price feed in LIVE_READ_ONLY."
                )
                self.price_feed = DeterministicPriceFeed()
            else:
                self.market_data_hub = MarketDataHub(
                    event_collector=self.event_collector,
                    broker=IbkrBroker(),
                    max_symbols_per_cycle=get_config("IBKR_MAX_SYMBOLS_PER_CYCLE"),
                )
                self.price_feed = MarketDataPriceFeed(self.market_data_hub)
                print("[MARKET_DATA] Market data source: IBKR (READ_ONLY)")
        elif self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO, RunMode.PAPER}:
            from src.brokers import IbkrBroker

            if IbkrBroker is not None:
                self.market_data_hub = MarketDataHub(
                    event_collector=self.event_collector,
                    broker=IbkrBroker(),
                    max_symbols_per_cycle=get_config("IBKR_MAX_SYMBOLS_PER_CYCLE"),
                )
                self.price_feed = MarketDataPriceFeed(self.market_data_hub)
            else:
                self.price_feed = DeterministicPriceFeed()
        else:
            self.price_feed = DeterministicPriceFeed()
        self.scanner_mode = get_config("SCANNER_MODE")
        if self.run_mode == RunMode.LIVE_READ_ONLY and self.market_data_hub is not None:
            self.scanner_mode = "LIVE_READONLY"
        elif self.run_mode == RunMode.LIVE_READ_ONLY:
            print("[SCAN][WARN] LIVE_READ_ONLY fallback to teaching scanner mode.")
        self.last_scanner_watchlist_payload = {}
        self.market_data_client = None
        if self.scanner_mode == "LIVE_READONLY":
            self.market_data_client = MarketDataClient()
            self.scanner = LiveReadOnlyScanner(
                market_data_client=self.market_data_client,
                event_collector=self.event_collector,
            )
            print("[SCAN] LiveReadOnlyScanner enabled — using IBKR read-only market data")
            print("[SCAN] Scanner type: LiveReadOnlyScanner")
        else:
            self.scanner = Scanner(
                event_collector=self.event_collector,
                market_data_hub=self.market_data_hub,
            )
        self.pattern_engine = PatternEngine()
        self.signal_engine_v1 = SignalEngineV1()
        print("[BOOT] SignalEngineV1 instantiated")
        self.strategy_runner = StrategyRunner(event_collector=self.event_collector)
        self.regime_layer = RegimeLayer(event_collector=self.event_collector)
        self.risk_engine = RiskEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            stop_controller=self.stop_controller,
        )
        if not self.execution_enabled:
            broker = None
        elif self.run_mode == RunMode.SIM:
            broker = SimBroker(
                gateway=OrderGateway(),
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )
        elif self.run_mode in {RunMode.LIVE_MICRO, RunMode.PAPER}:
            if IbkrLiveBroker is None:
                print(
                    "[EXECUTION][WARN] IBKR live broker unavailable; "
                    "forcing execution disabled for safety."
                )
                self.execution_enabled = False
                broker = None
            else:
                broker = IbkrLiveBroker(
                    event_collector=self.event_collector,
                    trade_registry=self.trade_registry,
                    run_mode=self.run_mode,
                )
        else:
            broker = None
        self.execution_engine = ExecutionEngine(
            broker=broker,
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            price_feed=self.price_feed,
            stop_controller=self.stop_controller,
        )
        self.execution_enabled = self.execution_engine.execution_enabled
        self.trade_exit_engine = TradeExitEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            price_feed=self.price_feed,
            stop_controller=self.stop_controller,
        )
        self.storage_engine = StorageEngine()
        self.learning_scheduler = LearningScheduler()
        self._halted = False
        self._degraded = False
        self._last_intent_validation = {"ok": True, "before": 0, "after": 0, "dropped": 0}
        self._daily_loss_warning_date: Optional[str] = None
        self._daily_loss_hard_stop_date: Optional[str] = None
        print(f"[BOOT] Event replay mode resolved — mode={self.replay_mode.value}")
        self._run_startup_validations()
        try:
            self.learning_scheduler.on_startup()
        except Exception as exc:
            print(f"[LEARNING][SCHEDULER] Startup check failed: {exc}")

    @staticmethod
    def _strategy_mode_for_session_phase(session_phase: str) -> str:
        if session_phase in {"PREMARKET", "OPENING_0_30", "MORNING"}:
            return "OPEN_FAST"
        if session_phase in {"LATE", "POWER_HOUR"}:
            return "LATE_SLOW"
        return "MIDDAY_SLOW"

    @staticmethod
    def _build_scanner_policy(session_phase: str) -> tuple[RossMomentumPolicy, StockSelectionPolicy]:
        strategy_policy = RossMomentumPolicy()
        stock_policy = stock_selection_policy_for_session_phase(strategy_policy, session_phase)
        return strategy_policy, stock_policy

    @staticmethod
    def _build_scanner_request(stock_policy: StockSelectionPolicy) -> ScannerRequest:
        override_symbols = None
        if stock_policy.universe.source == UniverseSource.CONFIG_SYMBOLS:
            override_symbols = get_config("SCANNER_SYMBOLS")
        return scanner_request_from_policy(stock_policy, optional_symbols_override=override_symbols)

    def _build_strategy_context(
        self,
        *,
        now: datetime,
        ny_time: datetime,
        uk_time: datetime,
        session_phase: str,
        watchlist_rows: List[object],
        watchlist_k: List[str],
        focus_m: List[str],
    ) -> StrategyContext:
        mode = self._strategy_mode_for_session_phase(session_phase)
        symbols: Dict[str, SymbolContext] = {}
        for row in watchlist_rows:
            symbol = getattr(row, "symbol", None)
            if not symbol:
                continue
            md = SymbolMarketData(
                last=getattr(row, "last_price", None),
                bid=getattr(row, "bid", None),
                ask=getattr(row, "ask", None),
                spread=getattr(row, "spread", None),
                day_volume=getattr(row, "volume", None),
                rel_volume=getattr(row, "rvol", None),
            )
            ind = SymbolIndicators(
                rvol=getattr(row, "rvol", None),
                float_shares=getattr(row, "float_shares", None),
            )
            symbols[symbol] = SymbolContext(
                symbol=symbol,
                timestamp=now,
                mode=mode,
                md=md,
                ind=ind,
                data_quality_flags=list(getattr(row, "data_quality_flags", []) or []),
            )
        return StrategyContext(
            now=now,
            ny_time=ny_time,
            uk_time=uk_time,
            session_phase=session_phase,
            mode=mode,
            symbols=symbols,
            watchlist_k=watchlist_k,
            focus_m=focus_m,
        )

    def replay_events(self, events):
        self.replay_engine.replay(events)

    def replay_cycle_events(self):
        print("[REPLAY] Initiating cycle-scoped replay")
        self.replay_events(self.event_collector.snapshot_cycle())

    def replay_all_events(self):
        print("[REPLAY] Initiating full-run replay")
        self.replay_events(self.event_collector.snapshot_all())

    def _check_live_micro_circuit_breakers(self) -> bool:
        if self.run_mode != RunMode.LIVE_MICRO:
            return True

        if self.stop_controller.is_breaker_tripped():
            print("[CIRCUIT_BREAKER] Latched breaker active — execution remains disabled.")
            return True

        net_realised_pnl = self.event_collector.sum_realised_pnl()
        trades_submitted = self.event_collector.count("ORDER_SUBMITTED")
        consecutive_losses = self.event_collector.consecutive_losses()

        max_trades = get_config("LIVE_MICRO_MAX_TRADES_PER_DAY")
        max_consecutive_losses = get_config("LIVE_MICRO_MAX_CONSECUTIVE_LOSSES")

        breaches = []
        if trades_submitted >= max_trades:
            breaches.append(f"MAX_TRADES_PER_DAY (submitted={trades_submitted})")
        if consecutive_losses >= max_consecutive_losses:
            breaches.append(
                f"MAX_CONSECUTIVE_LOSSES (consecutive_losses={consecutive_losses})"
            )

        if not breaches:
            return True

        breaker_details = {
            "limits": {
                "max_trades_per_day": max_trades,
                "max_consecutive_losses": max_consecutive_losses,
            },
            "metrics": {
                "net_realised_pnl": net_realised_pnl,
                "trades_submitted": trades_submitted,
                "consecutive_losses": consecutive_losses,
            },
            "breaches": breaches,
        }

        for breach in breaches:
            breaker_id = f"LIVE_MICRO_{breach.split(' ')[0]}"
            if not self.stop_controller.is_breaker_tripped(breaker_id):
                self.stop_controller.trip_breaker(
                    breaker_id=breaker_id,
                    reason=breach,
                    source="CircuitBreaker",
                    details=breaker_details,
                )
                self.event_collector.emit(
                    event_type="CIRCUIT_BREAKER_TRIGGERED",
                    source="CoreOrchestrator",
                    payload={
                        "run_mode": self.run_mode.value,
                        "breaches": breaches,
                        "limits": breaker_details["limits"],
                        "metrics": breaker_details["metrics"],
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
        reason = "Circuit breaker triggered: " + "; ".join(breaches)
        print(f"[CIRCUIT_BREAKER] {reason}")
        return True

    def _check_daily_loss_limits(self, ny_date: str) -> None:
        if self.run_mode not in {RunMode.LIVE_MICRO, RunMode.PAPER}:
            return

        daily_pnl = self.event_collector.daily_realised_pnl()
        warning_limit = abs(get_daily_loss_warning_limit())
        hard_limit = abs(get_daily_loss_hard_limit())

        if warning_limit > 0 and daily_pnl <= -warning_limit:
            if self._daily_loss_warning_date != ny_date:
                self._daily_loss_warning_date = ny_date
                print(
                    "[RISK][WARN] Daily loss warning threshold reached "
                    f"pnl={daily_pnl:.2f} limit=-{warning_limit:.2f}"
                )
                self.event_collector.emit(
                    event_type="DAILY_LOSS_WARNING",
                    source="CoreOrchestrator",
                    payload={
                        "run_mode": self.run_mode.value,
                        "daily_pnl": daily_pnl,
                        "warning_limit": warning_limit,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

        if hard_limit > 0 and daily_pnl <= -hard_limit:
            if self._daily_loss_hard_stop_date != ny_date:
                self._daily_loss_hard_stop_date = ny_date
                breaker_id = "DAILY_MAX_LOSS"
                if not self.stop_controller.is_breaker_tripped(breaker_id):
                    self.stop_controller.trip_breaker(
                        breaker_id=breaker_id,
                        reason=(
                            "Daily loss hard stop reached "
                            f"(pnl={daily_pnl:.2f}, limit=-{hard_limit:.2f})"
                        ),
                        source="RiskEngine",
                        details={
                            "daily_pnl": daily_pnl,
                            "hard_limit": hard_limit,
                            "run_mode": self.run_mode.value,
                        },
                    )
                print(
                    "[CIRCUIT_BREAKER] Daily loss hard stop triggered "
                    f"pnl={daily_pnl:.2f} limit=-{hard_limit:.2f}"
                )
                self.event_collector.emit(
                    event_type="CIRCUIT_BREAKER_TRIGGERED",
                    source="CoreOrchestrator",
                    payload={
                        "run_mode": self.run_mode.value,
                        "breaches": ["DAILY_MAX_LOSS"],
                        "limits": {"daily_loss_hard_limit": hard_limit},
                        "metrics": {"daily_pnl": daily_pnl},
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

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

        from src.config.system_config import (
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
                if self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO} and current_session == "CLOSED":
                    print(
                        "[GATE] RUN_MODE is LIVE/LIVE_MICRO while session is CLOSED. "
                        "Skipping orchestrator.run_once() to maintain teaching-first safety."
                    )
                    print(
                        "[GATE] Teaching note: SIM/PAPER would still run for education, "
                        "but LIVE/LIVE_MICRO waits for an open session."
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
        cycle_started_at = datetime.now(timezone.utc)
        ny_time = to_ny_time(cycle_started_at)
        uk_time = to_uk_time(cycle_started_at)
        session_phase = market_session_phase(cycle_started_at)
        print(
            "[SESSION] "
            f"phase={session_phase} ny_time={ny_time.isoformat()} "
            f"uk_time={uk_time.isoformat()} utc={cycle_started_at.isoformat()}"
        )
        strategy_policy, scanner_policy = self._build_scanner_policy(session_phase)
        scanner_request = self._build_scanner_request(scanner_policy)
        execution_intent = build_execution_intent(
            strategy_name=strategy_policy.name,
            mode=self.run_mode.value,
            session_phase=session_phase,
            policy=scanner_policy,
            execution_enabled=self.execution_enabled,
        )
        print(
            "[ORCH][POLICY] loaded strategy=ross_momentum "
            f"version={strategy_policy.version} policy={strategy_policy.name} "
            "stock_selection=ENABLED"
        )
        print(
            "[ORCH][POLICY] delegating to scanner "
            f"watchlist_k={scanner_policy.watchlist_limit_k} "
            f"focus_m={scanner_policy.focus_limit_m} "
            f"top_n={scanner_policy.top_gainers_n}"
        )
        print(
            "[ORCH][POLICY] scanner_universe="
            f"{scanner_request.universe_source.value} "
            f"scan_code={scanner_request.ibkr_scan_code} "
            f"top_n={scanner_request.requested_top_n}"
        )
        print(
            "[INTENT] "
            f"strategy={execution_intent.strategy_name} "
            f"mode={execution_intent.mode} "
            f"session_phase={execution_intent.session_phase} "
            f"trade_enabled={execution_intent.trade_enabled} "
            f"scan_only={execution_intent.scan_only} "
            f"enforcement={execution_intent.enforcement}"
        )
        tick = self.sim_clock.tick()
        print(f"[CYCLE_CTX] tick={tick} run_mode={self.run_mode.value}")
        self.execution_engine.current_tick = tick
        self.event_collector.clear_cycle()
        self.event_collector.roll_daily_pnl(cycle_started_at)
        ny_date = self.event_collector.daily_pnl_date()
        if ny_date and self._daily_loss_hard_stop_date and self._daily_loss_hard_stop_date != ny_date:
            if self.stop_controller.reset_breakers(
                open_positions=self.trade_registry.count_active(),
                reason="New trading day",
                source="CoreOrchestrator",
            ):
                self._daily_loss_warning_date = None
                self._daily_loss_hard_stop_date = None
        if self.market_data_hub is not None:
            self.market_data_hub.reset_cycle()
        event = self.event_collector.emit(
            event_type="CYCLE_START",
            source="Orchestrator",
            payload={"run_mode": self.run_mode}
        )
        print(event)
        if ny_date:
            self._check_daily_loss_limits(ny_date)
        self._evaluate_runtime_safety(
            cycle_stage="CYCLE_START",
            stage_exception=None,
        )
        if self._stop_requested_at_boundary("CYCLE_START"):
            return False

        print("[TEACH] >>> Scanner stage — gather candidates (conceptual).")
        try:
            scanner_results = self.scanner.run_scan_cycle(
                policy=scanner_policy,
                scanner_request=scanner_request,
            )
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="SCANNER",
                stage_exception=exc,
            )
            return False
        scanner_watchlist_payload = {}
        try:
            scanner_watchlist_payload = run_scanner_cycle(
                mode="integrated",
                policy=scanner_policy,
                scanner_request=scanner_request,
            )
            self.last_scanner_watchlist_payload = scanner_watchlist_payload
            self.event_collector.emit(
                event_type="SCANNER_WATCHLIST",
                source="Scanner",
                payload={
                    "scanner_version": scanner_watchlist_payload.get("scanner_version"),
                    "timestamp_utc": scanner_watchlist_payload.get("timestamp_utc"),
                    "symbols": scanner_watchlist_payload.get("symbols", []),
                },
            )
            try:
                stored = self.storage_engine.store_watchlist(
                    strategy_name=str(scanner_policy.policy_name),
                    session_phase=session_phase,
                    watchlist_symbols=list(scanner_watchlist_payload.get("watchlist_k", [])),
                    focus_symbols=list(scanner_watchlist_payload.get("focus_m", [])),
                    metrics_payload={
                        "watchlist_rows": scanner_watchlist_payload.get("watchlist_rows", []),
                        "focus_rows": scanner_watchlist_payload.get("focus_rows", []),
                        "drop_reason_summary": scanner_watchlist_payload.get(
                            "drop_reason_summary", {}
                        ),
                        "timestamp_utc": scanner_watchlist_payload.get("timestamp_utc"),
                    },
                )
                if stored:
                    print(
                        "[SCANNER][STORAGE] Watchlist persisted "
                        f"strategy={scanner_policy.policy_name} session={session_phase}"
                    )
            except Exception as exc:
                print(f"[SCANNER][STORAGE] Watchlist persistence failed: {exc}")
        except Exception as exc:
            print(f"[SCANNER] Integrated watchlist failed: {exc}")
        self._evaluate_runtime_safety(
            cycle_stage="SCANNER",
            stage_exception=None,
            scanner_results=scanner_results,
        )
        if self.run_mode == RunMode.LIVE_READ_ONLY:
            if self.scanner.last_connectivity_issue:
                print(
                    "[CONNECTIVITY] IBKR issue detected "
                    f"details={self.scanner.last_connectivity_issue}"
                )
                if self.scanner.auto_lockdown_enabled:
                    self._request_stop(
                        StopMode.PANIC,
                        reason="Connectivity degradation detected",
                        source="Scanner",
                    )
                    return False
                self._degraded = True
            if self.scanner.last_data_quality_flags:
                print(
                    "[DATA_QUALITY] Flags detected in live scan "
                    f"symbols={list(self.scanner.last_data_quality_flags.keys())}"
                )
                if self.scanner.auto_lockdown_enabled:
                    self._request_stop(
                        StopMode.PANIC,
                        reason="Data quality degradation detected",
                        source="Scanner",
                    )
                    return False
                self._degraded = True
                scanner_results = [
                    candidate
                    for candidate in scanner_results
                    if not candidate.data_quality_flags
                ]
        if self._stop_requested_at_boundary("SCANNER"):
            return False
        watchlist_k = list(scanner_watchlist_payload.get("watchlist_k", []))
        focus_m = list(scanner_watchlist_payload.get("focus_m", []))
        watchlist_rows = list(scanner_watchlist_payload.get("watchlist_rows", []))
        strategy_context = self._build_strategy_context(
            now=cycle_started_at,
            ny_time=ny_time,
            uk_time=uk_time,
            session_phase=session_phase,
            watchlist_rows=watchlist_rows,
            watchlist_k=watchlist_k,
            focus_m=focus_m,
        )
        print(
            "[ORCH][CTX] "
            f"watchlist_k={len(strategy_context.watchlist_k)} "
            f"focus_m={len(strategy_context.focus_m)} "
            f"symbols_in_context={len(strategy_context.symbols)}"
        )
        focus_set = set(strategy_context.focus_m)
        if focus_set:
            scanner_results = [
                candidate for candidate in (scanner_results or [])
                if candidate.symbol in focus_set
            ]

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
        print("[TEACH] <<< Pattern stage complete — moving to signals stage.")
        if self._stop_requested_at_boundary("PATTERN"):
            return False

        print("[TEACH] >>> Signals stage — evaluate momentum triggers (teaching).")
        signals = self.signal_engine_v1.generate(
            scanner_output=scanner_results or [],
            pattern_output=pattern_results or [],
            tick=tick,
        )
        print(f"[SIGNALS] total={len(signals)}")
        for signal in signals:
            print(
                "[SIGNAL] "
                f"symbol={signal.symbol} type={signal.signal_type.value} "
                f"strength={signal.strength:.2f}"
            )
        event = self.event_collector.emit(
            event_type="SIGNALS_GENERATED",
            source="SignalEngineV1",
            payload={"signals": len(signals)},
        )
        print(event)
        print("[TEACH] <<< Signals stage complete — moving to strategy stage.")

        regime_snapshot = None
        regime_policy_decision = None
        if self.regime_layer.enabled:
            print("[TEACH] >>> Regime stage — classify market regime (adaptive layer).")
            regime_snapshot, regime_policy_decision = self.regime_layer.evaluate(
                candidates=scanner_results or [],
                session=get_current_market_session(),
            )
            print("[TEACH] <<< Regime stage complete — moving to strategy stage.")

        print("[TEACH] >>> Strategy stage — decide on trade ideas (conceptual).")
        try:
            filtered_pattern_results = self.strategy_runner.filter_pattern_results(
                pattern_results or [],
                strategy_context.focus_m,
            )
            strategy_intents = self.strategy_runner.generate_trade_intents(
                filtered_pattern_results,
                policy_decision=regime_policy_decision,
                signals=signals,
            )
            strategy_output = self.strategy_runner.run_from_intents(strategy_intents)
            strategy_output = self._merge_trade_intents([], strategy_output)
            strategy_output = self._annotate_trade_intents_with_regime(
                strategy_output,
                regime_snapshot,
                regime_policy_decision,
            )
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
            for trade_intent in strategy_output:
                self.strategy_perf_tracker.record_trade_attempt(
                    getattr(trade_intent, "strategy_name", "UNKNOWN")
                )
        print("[TEACH] <<< Strategy stage complete — moving to risk stage.")

        print("[TEACH] >>> Intent normalization stage — enforce deduplication.")
        try:
            strategy_output = self._normalize_trade_intents(strategy_output)
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="INTENT_NORMALISATION",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
            )
            return False
        self._evaluate_runtime_safety(
            cycle_stage="INTENT_NORMALISATION",
            stage_exception=None,
            scanner_results=scanner_results,
            pattern_results=pattern_results,
            strategy_output=strategy_output,
        )
        print("[TEACH] <<< Intent normalization stage complete — moving to risk stage.")

        print("[TEACH] >>> Risk stage — check sizing and limits (conceptual).")
        risk_output: List[RiskDecision] = []
        blocked_symbols: set[str] = set()
        risk_multiplier = (
            regime_policy_decision.risk_multiplier
            if regime_policy_decision and regime_policy_decision.applied
            else None
        )
        if not strategy_output:
            print("[RISK] No risk decision produced — placeholder outcome.")
        else:
            print(
                f"[TEACH] Risk engine will evaluate {len(strategy_output)} trade intents individually."
            )
            try:
                for trade_intent in strategy_output:
                    if trade_intent.symbol in blocked_symbols:
                        print(
                            "[RISK] Skipping duplicate blocked intent for "
                            f"symbol={trade_intent.symbol} in this cycle."
                        )
                        continue
                    print(
                        f"[TEACH] Evaluating risk for symbol: {trade_intent.symbol} "
                        f"(trader_type={trade_intent.trader_type})"
                    )
                    if getattr(trade_intent, "tick", None) is None:
                        trade_intent.tick = tick
                    decision = self.risk_engine.evaluate_trade_intent(
                        trade_intent,
                        risk_multiplier=risk_multiplier,
                    )
                    decision.trader_type = getattr(trade_intent, "trader_type", "MANUAL")
                    if not decision.allowed or decision.risk_level == "BLOCKED":
                        blocked_symbols.add(trade_intent.symbol)
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

        execution_output: List[ExecutionResult] = []
        if execution_intent.scan_only:
            print("[EXECUTION] Execution stage skipped — intent scan_only.")
        elif not self.execution_enabled:
            print("[EXECUTION] Execution stage skipped — execution disabled.")
        else:
            print("[TEACH] >>> Execution stage — send/prepare orders (conceptual).")
            pending_results = self.execution_engine.process_pending_orders(tick)
            execution_output.extend(pending_results)
            if not risk_output:
                print("[EXECUTION] No execution result — placeholder outcome.")
            else:
                print(
                    f"[TEACH] Execution engine will handle {len(risk_output)} risk decisions individually."
                )
                for risk_decision in risk_output:
                    print(
                        f"[TEACH] Routing execution for symbol: {risk_decision.symbol} "
                        f"(trader_type={risk_decision.trader_type})"
                    )
                    try:
                        execution_output.append(
                            self.execution_engine.execute_trade(risk_decision)
                        )
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
                breaker_tripped=self.stop_controller.is_breaker_tripped(),
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

        cycle_events = self.event_collector.snapshot_cycle()
        closed_trade_events = [
            event for event in cycle_events if event.event_type == "TRADE_CLOSED"
        ]
        opened_trade_events = [
            event for event in cycle_events if event.event_type == "TRADE_OPENED"
        ]
        blocked_trade_events = [
            event for event in cycle_events if event.event_type == "TRADE_BLOCKED"
        ]

        self.performance_registry.record(cycle_events)
        performance_snapshot = self.performance_registry.snapshot(
            open_trades=self.trade_registry.count_active()
        )
        print(
            "[PERF] "
            f"closed={performance_snapshot.closed_trades} "
            f"open={performance_snapshot.open_trades} "
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
        for event in opened_trade_events:
            self.strategy_perf_tracker.record_trade_open(event.payload or {})
        for event in blocked_trade_events:
            self.strategy_perf_tracker.record_trade_blocked(event.payload or {})
        strategy_snapshots = self.strategy_perf_tracker.snapshot()
        strategy_perf_payload = [
            {
                "strategy_name": snapshot.strategy_name,
                "attempts": snapshot.attempts,
                "opened": snapshot.opened,
                "blocked": snapshot.blocked,
                "closed": snapshot.closed,
                "total_trades": snapshot.total_trades,
                "wins": snapshot.wins,
                "losses": snapshot.losses,
                "flats": snapshot.flats,
                "gross_pnl": snapshot.gross_pnl,
                "net_pnl": snapshot.net_pnl,
                "total_commissions": snapshot.total_commissions,
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
        if not self._check_live_micro_circuit_breakers():
            return False

        print("[TEACH] >>> Storage stage — record decisions/results (conceptual).")
        print("[TEACH] Creating TradeRecord to capture stage outputs for review.")
        cycle_ended_at = datetime.now(timezone.utc)
        cycle_context = {
            "tick": tick,
            "session": get_current_market_session(),
            "cycle_started_at": cycle_started_at,
            "cycle_ended_at": cycle_ended_at,
        }
        try:
            trade_record = TradeRecord(
                scanner_output=scanner_results or [],
                pattern_output=pattern_results or [],
                strategy_output=strategy_output or [],
                risk_output=risk_output or [],
                execution_output=execution_output or [],
                trade_outcomes=trade_outcomes or [],
                performance_snapshot=performance_snapshot,
                regime_snapshot=regime_snapshot.to_payload() if regime_snapshot else None,
                regime_policy_decision=(
                    regime_policy_decision.to_payload() if regime_policy_decision else None
                ),
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
            storage_result = self.storage_engine.store_trade_record(
                trade_record,
                cycle_context=cycle_context,
                events=self.event_collector.snapshot_cycle(),
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

        cycle_events = self.event_collector.snapshot_cycle()
        expected_events = len(cycle_events)
        storage_ok = True
        events_ok = True
        if self.storage_engine.enabled and self.storage_engine.backend == "sqlite":
            storage_ok = storage_result.ok
            events_ok = (
                storage_result.ok
                and storage_result.events_persisted == expected_events
            )
        intent_ok = self._last_intent_validation.get("ok", True)
        market_data_status, market_data_ok = self._resolve_market_data_status()

        print(
            "[VALIDATION][SUMMARY] "
            f"storage={'OK' if storage_ok else 'FAIL'} "
            f"intent={'OK' if intent_ok else 'FAIL'} "
            f"market_data={market_data_status} "
            f"events={'OK' if events_ok else 'FAIL'}"
        )
        if market_data_status == "FAIL":
            raise RuntimeError("Market data validation failed; halting cycle")
        if not all([storage_ok, intent_ok, market_data_ok, events_ok]):
            raise RuntimeError("Validation summary failed; halting cycle")

        print(
            "[SUMMARY] "
            f"scanner={len(scanner_results or [])} | "
            f"patterns={len(pattern_results or [])} | "
            f"trade_intents={len(strategy_output or [])} | "
            f"risk_decisions={len(risk_output or [])} | "
            f"execution_results={len(execution_output or [])}"
        )

        print("[INFO] Orchestrator cycle complete (teaching-only).")
        cycle_snapshot = cycle_events
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
                    f"attempts={snapshot.attempts} "
                    f"opened={snapshot.opened} "
                    f"blocked={snapshot.blocked} "
                    f"closed={snapshot.closed} "
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
        if self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
            print(
                "[REPLAY] Replay is locked down in LIVE/LIVE_READ_ONLY/LIVE_MICRO — skipping replay"
            )
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
        merged: Dict[Tuple[str, str], TradeIntent] = {}
        sources: Dict[Tuple[str, str], str] = {}

        def consider(intent: TradeIntent, source: str) -> None:
            key = (intent.symbol, intent.trader_type)
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

    def _annotate_trade_intents_with_regime(
        self,
        intents: List[TradeIntent],
        snapshot,
        policy_decision,
    ) -> List[TradeIntent]:
        if not snapshot:
            return intents
        annotated: List[TradeIntent] = []
        for intent in intents:
            annotated.append(
                replace(
                    intent,
                    regime_label=snapshot.label.value,
                    regime_confidence=snapshot.confidence,
                    regime_policy_applied=bool(
                        policy_decision.applied if policy_decision else False
                    ),
                    regime_notes=list(policy_decision.notes)
                    if policy_decision
                    else [],
                )
            )
        return annotated

    def _normalize_trade_intents(self, intents: List[TradeIntent]) -> List[TradeIntent]:
        intents_to_process = list(intents)
        injected_duplicates = 0
        if get_config("INTENT_DEDUP_SELFTEST_ENABLED") and intents_to_process:
            base_intent = intents_to_process[0]
            lowered_confidence = max((base_intent.confidence or 0.0) - 0.01, 0.0)
            duplicate = replace(base_intent, confidence=lowered_confidence)
            intents_to_process.append(duplicate)
            injected_duplicates = 1
            print(
                "[INTENT][SELFTEST] Injected duplicate intent for "
                f"symbol={base_intent.symbol} trader_type={base_intent.trader_type} "
                f"direction={base_intent.direction}"
            )
        before_count = len(intents_to_process)
        deduped: Dict[Tuple[str, str, str], TradeIntent] = {}
        for intent in intents_to_process:
            key = (intent.symbol, intent.trader_type, intent.direction)
            current = deduped.get(key)
            if current is None or intent.confidence > current.confidence:
                deduped[key] = intent

        dropped = len(intents_to_process) - len(deduped)
        for intent in intents_to_process:
            key = (intent.symbol, intent.trader_type, intent.direction)
            kept = deduped.get(key)
            if kept is None or kept is intent:
                continue
            self.event_collector.emit(
                event_type="INTENT_DROPPED_DUPLICATE",
                source="CoreOrchestrator",
                payload={
                    "symbol": intent.symbol,
                    "trader_type": intent.trader_type,
                    "direction": intent.direction,
                    "kept_confidence": kept.confidence,
                    "dropped_confidence": intent.confidence,
                    "reason": "Lower confidence duplicate dropped",
                },
            )

        normalized = list(deduped.values())
        normalized_keys = [
            (intent.symbol, intent.trader_type, intent.direction) for intent in normalized
        ]
        if len(set(normalized_keys)) != len(normalized_keys):
            self._last_intent_validation = {
                "ok": False,
                "before": before_count,
                "after": len(normalized),
                "dropped": dropped,
            }
            raise RuntimeError("Intent deduplication failed — duplicates remain")

        self.event_collector.emit(
            event_type="INTENT_NORMALISED",
            source="CoreOrchestrator",
            payload={
                "before_count": before_count,
                "after_count": len(normalized),
                "duplicates_dropped": dropped,
            },
        )
        print(
            "[INTENT][VALIDATION] Deduplication OK — "
            f"before={before_count} after={len(normalized)} duplicates_dropped={dropped}"
        )
        if get_config("INTENT_DEDUP_SELFTEST_ENABLED"):
            if injected_duplicates < 1 or dropped < injected_duplicates:
                raise RuntimeError(
                    "Intent dedup self-test failed — duplicates were not dropped"
                )
            print(
                "[INTENT][SELFTEST] injected_duplicates="
                f"{injected_duplicates} dropped={dropped} OK"
            )
        self._last_intent_validation = {
            "ok": True,
            "before": before_count,
            "after": len(normalized),
            "dropped": dropped,
        }
        return normalized

    def _run_startup_validations(self) -> None:
        print("[VALIDATION] Running startup validations")
        print("[VALIDATION] Config resolved")
        print(f"[VALIDATION] Effective run mode: {self.run_mode.value}")
        print(f"[VALIDATION] Scanner type selected: {type(self.scanner).__name__}")
        if self.run_mode == RunMode.SIM:
            market_data_source = "SIM"
        elif self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO, RunMode.PAPER}:
            market_data_source = "IBKR"
            if self.run_mode == RunMode.LIVE_READ_ONLY and self.market_data_hub is None:
                market_data_source = "SIM_FALLBACK"
        else:
            market_data_source = "SIM"
        execution_policy = "ALLOWED" if self.execution_enabled else "HARD DISABLED"
        print(f"[VALIDATION] Execution policy: {execution_policy}")
        print(f"[VALIDATION] Market data source: {market_data_source}")
        print(
            "[VALIDATION] IBKR API WRITE: "
            f"{'ENABLED' if self.ibkr_api_write_allowed else 'DISABLED'}"
        )
        print(
            "[VALIDATION] EXECUTION: "
            f"{'ENABLED' if self.execution_enabled else 'HARD DISABLED'}"
        )
        print(
            "[VALIDATION] ORDER ROUTING: "
            f"{'ALLOWED' if self.execution_enabled else 'BLOCKED'}"
        )
        if self.run_mode == RunMode.LIVE_MICRO and self.execution_enabled:
            if not get_live_micro_ack():
                raise RuntimeError("LIVE_MICRO_ACK required for LIVE_MICRO execution.")
            if not get_live_micro_1_share_only():
                raise RuntimeError("LIVE_MICRO_1_SHARE_ONLY required for LIVE_MICRO execution.")
        if market_data_source == "IBKR":
            print("[VALIDATION] MARKET DATA: LIVE IBKR")
        broker_adapter = getattr(self.execution_engine, "broker", None)
        broker_name = (
            broker_adapter.name()
            if broker_adapter is not None and hasattr(broker_adapter, "name")
            else type(broker_adapter).__name__ if broker_adapter is not None else "NONE"
        )
        print(f"[VALIDATION] Broker adapter in use: {broker_name}")
        if self.run_mode == RunMode.LIVE_READ_ONLY:
            if self.run_mode == RunMode.SIM:
                raise RuntimeError(
                    "RUN_MODE=SIM is invalid when IBKR live/read-only settings are active."
                )
            if market_data_source == "SIM_FALLBACK":
                print("[VALIDATION][WARN] LIVE_READ_ONLY using SIM fallback market data.")
            elif "SIM" in market_data_source:
                raise RuntimeError(
                    "Market data source resolved to SIM under LIVE_READ_ONLY conditions."
                )
            if isinstance(broker_adapter, SimBroker):
                raise RuntimeError("SIM broker instantiated under LIVE_READ_ONLY conditions.")
        if self.run_mode == RunMode.LIVE_READ_ONLY:
            print("[VALIDATION] LIVE_READ_ONLY: live data enabled")
            print("[VALIDATION] LIVE_READ_ONLY: execution disabled by design")
            if self.market_data_hub is None:
                print(
                    "[VALIDATION][WARN] LIVE_READ_ONLY fallback active: "
                    "MarketDataHub unavailable."
                )
            else:
                if not isinstance(self.scanner, LiveReadOnlyScanner):
                    raise RuntimeError("LIVE_READ_ONLY must use LiveReadOnlyScanner")
                if not isinstance(self.price_feed, MarketDataPriceFeed):
                    raise RuntimeError("LIVE_READ_ONLY must use MarketDataPriceFeed")
        if self.storage_engine.enabled and self.storage_engine.backend == "sqlite":
            if self.storage_engine._store is None:
                raise RuntimeError("Storage engine failed to open SQLite store")
            print("[VALIDATION] Storage OK — SQLite opened")
        if self.scanner_mode == "LIVE_READONLY":
            if not hasattr(self.scanner, "validate_startup"):
                raise RuntimeError("LiveReadOnlyScanner missing startup validation hook")
            self.scanner.validate_startup()
            print("[VALIDATION] Market data connectivity OK")

    def _resolve_market_data_status(self) -> tuple[str, bool]:
        if self.scanner_mode == "TEACHING":
            return "N/A", True
        if self.scanner_mode != "LIVE_READONLY":
            return "OK", True
        if self.scanner.last_connectivity_issue:
            return "FAIL", False
        success_count = getattr(self.scanner, "last_snapshot_success_count", 0)
        attempt_count = getattr(self.scanner, "last_snapshot_attempted_count", 0)
        if success_count > 0:
            return "OK", True
        if attempt_count > 0:
            return "DEGRADED", True
        return "DEGRADED", True

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
            mode = (
                StopMode.PANIC
                if self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}
                else StopMode.GRACEFUL
            )
            self._request_stop(
                mode,
                reason=f"Fault: {fault.message}",
                source="FaultRecovery",
            )
            return False
        return False

    def _emit_ops_summary(self) -> None:
        opened = self.event_collector.count("TRADE_OPENED")
        closed = self.event_collector.count("TRADE_CLOSED")
        intents = self.event_collector.count("INTENT_NORMALISED")
        if not any([opened, closed, intents]):
            return
        realised_pnl = self.event_collector.sum_realised_pnl()
        commissions = 0.0
        for event in self.event_collector.filter_by_type("TRADE_CLOSED"):
            payload = event.payload or {}
            try:
                commissions += float(payload.get("commission", 0.0))
            except (TypeError, ValueError):
                continue
        watchlist = self.last_scanner_watchlist_payload.get("watchlist_k", [])
        focus = self.last_scanner_watchlist_payload.get("focus_m", [])
        ny_date = to_ny_time(datetime.now(timezone.utc)).date().isoformat()
        summary = {
            "asof_date_ny": ny_date,
            "run_mode": self.run_mode.value,
            "scanner": {
                "symbols_scanned": len(self.last_scanner_watchlist_payload.get("symbols", [])),
                "watchlist_size": len(watchlist),
                "focus_size": len(focus),
                "last_watchlist_hash": self.storage_engine.last_watchlist_hash,
            },
            "trades": {
                "opened": opened,
                "closed": closed,
                "realised_pnl": realised_pnl,
                "commissions": round(commissions, 2),
            },
            "risk": {
                "daily_loss_warning_date": self._daily_loss_warning_date,
                "daily_loss_hard_stop_date": self._daily_loss_hard_stop_date,
                "circuit_breakers_tripped": len(self.stop_controller.breaker_snapshot()),
            },
        }
        print("[OPS][SUMMARY]", summary)
        report_dir = "data/reports/ops"
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"{ny_date}_ops_summary.json")
        try:
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2, sort_keys=True)
        except Exception as exc:
            print(f"[OPS][SUMMARY] Failed to write report: {exc}")

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
        try:
            self._emit_ops_summary()
        except Exception as exc:
            print(f"[OPS][SUMMARY] Failed to emit ops summary: {exc}")
        try:
            self.learning_scheduler.on_shutdown()
        except Exception as exc:
            print(f"[LEARNING][SCHEDULER] Shutdown check failed: {exc}")
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
            "INTENT_NORMALISATION",
            "RISK",
            "EXECUTION",
            "EXIT_SIGNALS",
            "TRADE_EXIT",
            "STORAGE",
            "INVARIANTS",
        }
        stage_label = cycle_stage or "UNKNOWN"

        if (
            self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}
            and self.replay_mode != EventReplayMode.OFF
        ):
            violations.append("Replay requested while in LIVE/LIVE_READ_ONLY/LIVE_MICRO mode")
        if self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO} and isinstance(
            self.sim_clock, SimClock
        ):
            violations.append("Deterministic SimClock detected in LIVE/LIVE_MICRO mode")
        if self.run_mode in {RunMode.LIVE, RunMode.LIVE_MICRO} and isinstance(
            self.price_feed, DeterministicPriceFeed
        ):
            violations.append("Deterministic price feed detected in LIVE/LIVE_MICRO mode")

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

        if self.run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
            print(
                "[SAFETY] LIVE/LIVE_READ_ONLY/LIVE_MICRO mode violation — entering deterministic safe halt."
            )
            self._request_stop(
                StopMode.PANIC,
                reason="Runtime safety violation",
                source="RuntimeSafety",
            )
            return

        raise RuntimeSafetyError("; ".join(violations))
