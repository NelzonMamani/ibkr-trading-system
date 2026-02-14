"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4
from typing import Dict, List, Optional, Set, Tuple

from src.brokers import IbkrLiveBroker, SimBroker
from src.config.config_resolver import emit_config_event, get_config
from src.config.runtime_config import (
    EventReplayMode,
    RunMode,
    get_daily_loss_hard_limit,
    get_daily_loss_warning_limit,
    get_run_mode,
    get_scanner_mode,
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
from src.core.trace_bus import TraceBus
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import IbkrExecutionProvider, PaperExecutionProvider
from src.core.managers import (
    ConnectionManager,
    MarketDataSnapshotManager,
    RuntimeModeManager,
    ScannerDiagnosticsManager,
)
from src.execution.trade_exit_engine import TradeExitEngine
from src.learning.scheduler import LearningScheduler
from src.market_data.market_data_hub import MarketDataHub
from src.market_data.market_data_price_feed import MarketDataPriceFeed
from src.performance.strategy_performance import StrategyPerformanceTracker
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import ExecutionResult, RiskDecision, TradeIntent, TradeRecord
from src.patterns.pattern_engine import PatternEngine
from src.risk.risk_engine import RiskEngine
from src.core.intent import build_decision_artifact, build_execution_intent
from src.e22.strategy_scalability_and_arbitration import (
    E22PolicyConfig,
    apply_e22_arbitration_layer,
)
from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_contract import ScannerRequest, scanner_request_from_policy
from src.scanner.ranking_registry import resolve_watchlist_selector
from src.scanner.result_models import CandidateMetrics
from src.scanner.scanner_runner import run_scanner_cycle
from src.scanner.providers.base import ProviderConnectionError
from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.session_pct_change import normalize_session_label
from src.sim.clock import SimClock, WallClock
from src.sim.price_feed import DeterministicPriceFeed
from src.signals.signal_engine_v1 import SignalEngineV1
from src.storage.storage_engine import StorageEngine
from src.strategy.strategy_runner import StrategyRunner
from src.strategy.exit_signal import ExitSignal
from src.strategy_portfolio.adapters.ross_momentum_adapter import (
    ross_trade_intents_to_decision_intents,
)
from src.prep.premarket_prep import PreMarketPrepEngine
from src.events.event_invariants import check_invariants, EventInvariantError
from src.strategies.ross_momentum.strategy_context_schema import (
    StrategyContext,
    SymbolContext,
    SymbolIndicators,
    SymbolMarketData,
)
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    StockSelectionSpec,
    UniverseSource,
    stock_selection_policy_for_session_phase,
)
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    StatisticalIntradayMomentumPolicy,
    statistical_stock_selection_spec,
)
from src.strategies.mean_reversion.scanner_policy import (
    MeanReversionScannerPolicy,
    mean_reversion_stock_selection_spec,
)
from src.strategies.strategy_registry import StrategyRegistry, build_default_registry
from src.utils.time_utils import market_session_phase, to_ny_time, to_uk_time
from src.regime.layer import RegimeLayer


class RuntimeSafetyError(RuntimeError):
    """Raised when a runtime safety gate is violated."""


def build_orchestrator_strategy_registry(
    enabled_strategy_ids: Optional[List[str]] = None,
) -> StrategyRegistry:
    """Expose the canonical registry for orchestrator integration smoke tests."""
    return build_default_registry(enabled_strategy_ids=enabled_strategy_ids)


class CoreOrchestrator:
    def __init__(self):
        print("[INFO] Core Orchestrator initialised.")
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        self.run_mode = self.runtime_mode_manager.resolved_mode
        self.execution_enabled = self.runtime_mode_manager.allow_orders
        self.ibkr_api_write_allowed = bool(get_config("IBKR_API_WRITE_ALLOWED"))
        self.replay_mode = self.runtime_mode_manager.event_replay_mode
        print(f"[BOOT] Runtime mode resolved: {self.runtime_mode_manager.describe()}")
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[SAFETY] ORDER ROUTING: BLOCKED")
        if self.run_mode == RunMode.PAPER:
            print("[SAFETY] PAPER-EXECUTION MODE ACTIVE")
        if self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY, RunMode.PAPER}:
            self.sim_clock = WallClock()
        else:
            self.sim_clock = SimClock()
        self.event_collector = EventCollector()
        emit_config_event(self.event_collector)
        self.stop_controller = StopController()
        print("[BOOT] EventCollector initialised")
        self._last_market_session: str | None = None
        self.replay_engine = ReplayEngine()
        self.performance_registry = PerformanceRegistry()
        self.trade_registry = ActiveTradeRegistry()
        self.strategy_perf_tracker = StrategyPerformanceTracker()
        self.market_data_hub = None
        self.prep_engine = PreMarketPrepEngine(event_collector=self.event_collector)
        self.connection_manager = ConnectionManager(self.run_mode)
        self.scanner_diagnostics_manager = ScannerDiagnosticsManager()
        self.market_data_snapshot_manager: MarketDataSnapshotManager | None = None
        self.selected_strategy_key = (
            str(get_config("SELECTED_STRATEGY") or "ross_momentum").strip().lower()
            or "ross_momentum"
        )
        if self.run_mode == RunMode.READ_ONLY:
            from src.brokers import IbkrBroker

            if IbkrBroker is None:
                print(
                    "[MARKET_DATA][WARN] IbkrBroker unavailable; "
                    "falling back to deterministic price feed in READ_ONLY."
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
        elif self.run_mode in {RunMode.LIVE, RunMode.PAPER}:
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
        self.scanner_mode = get_scanner_mode()
        self.last_scanner_watchlist_payload = {}
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
            provider = None
        elif self.run_mode == RunMode.PAPER:
            provider = PaperExecutionProvider(
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )
        elif self.run_mode == RunMode.LIVE:
            if IbkrLiveBroker is None:
                print(
                    "[EXECUTION][WARN] IBKR live broker unavailable; "
                    "forcing execution disabled for safety."
                )
                self.execution_enabled = False
                provider = None
            else:
                broker = IbkrLiveBroker(
                    event_collector=self.event_collector,
                    trade_registry=self.trade_registry,
                    run_mode=self.run_mode,
                )
                provider = IbkrExecutionProvider(
                    broker=broker,
                    trade_registry=self.trade_registry,
                    run_mode=self.run_mode,
                )
        else:
            provider = None
        self.execution_engine = ExecutionEngine(
            provider=provider,
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
        self._current_cycle_id: Optional[str] = None
        self._last_halt_reason: Optional[dict] = None
        self.trace_bus = TraceBus()
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
    def _build_scanner_policy(session_phase: str) -> tuple[object, StockSelectionPolicy]:
        selected_strategy = (
            str(get_config("SELECTED_STRATEGY") or "ross_momentum").strip().lower()
            or "ross_momentum"
        )
        if selected_strategy == "statistical_intraday_momentum":
            strategy_policy = StatisticalIntradayMomentumPolicy()
            stock_policy = statistical_stock_selection_spec()
            return strategy_policy, stock_policy
        if selected_strategy == "mean_reversion":
            strategy_policy = MeanReversionScannerPolicy()
            stock_policy = mean_reversion_stock_selection_spec()
            return strategy_policy, stock_policy
        strategy_policy = RossMomentumPolicy()
        stock_policy = stock_selection_policy_for_session_phase(strategy_policy, session_phase)
        return strategy_policy, stock_policy

    @staticmethod
    def _build_scanner_request(
        stock_policy: StockSelectionPolicy,
        *,
        strategy_name: str,
        session_phase: str,
    ) -> ScannerRequest:
        override_symbols = None
        if stock_policy.universe.source == UniverseSource.CONFIG_SYMBOLS:
            override_symbols = get_config("SCANNER_SYMBOLS")
        request = scanner_request_from_policy(
            stock_policy,
            optional_symbols_override=override_symbols,
            strategy_name=strategy_name,
            session_phase=session_phase,
        )
        if request.policy_name == "ROSS_MOMENTUM":
            print(
                "[ORCH][SCANNER_REQUEST] "
                f"strategy={request.strategy_name} policy={request.policy_name} "
                f"instrument={request.instrument} locationCode={request.location_code} "
                f"scanCode={request.ibkr_scan_code} numberOfRows={request.requested_top_n} "
                f"abovePrice={request.above_price} belowPrice={request.below_price}"
            )
        return request

    def _build_strategy_context(
        self,
        *,
        now: datetime,
        ny_time: datetime,
        uk_time: datetime,
        session_phase: str,
        watchlist_rows: List[object],
        watchlist_k: List[CandidateMetrics],
        focus_m: List[CandidateMetrics],
        snapshots_by_symbol: Optional[Dict[str, MarketSnapshot]] = None,
    ) -> StrategyContext:
        mode = self._strategy_mode_for_session_phase(session_phase)
        symbols: Dict[str, SymbolContext] = {}
        for row in watchlist_rows:
            symbol = getattr(row, "symbol", None)
            if not symbol:
                continue
            snapshot = (snapshots_by_symbol or {}).get(symbol)
            last_price = getattr(row, "last_price", None)
            bid = getattr(row, "bid", None)
            ask = getattr(row, "ask", None)
            spread = getattr(row, "spread", None)
            day_volume = getattr(row, "volume", None)
            if snapshot is not None:
                last_price = snapshot.last or last_price
                bid = snapshot.bid if snapshot.bid is not None else bid
                ask = snapshot.ask if snapshot.ask is not None else ask
                day_volume = snapshot.volume if snapshot.volume is not None else day_volume
            prep_snapshot = self.prep_engine.get_snapshot(symbol)
            data_quality_flags = list(getattr(row, "data_quality_flags", []) or [])
            if prep_snapshot is None:
                data_quality_flags.append("PREP_SNAPSHOT_MODE")
            elif prep_snapshot.data_quality_flags:
                data_quality_flags.extend(prep_snapshot.data_quality_flags)
            md = SymbolMarketData(
                last=last_price,
                bid=bid,
                ask=ask,
                spread=spread,
                day_volume=day_volume,
                rel_volume=getattr(row, "rvol", None),
            )
            float_shares = getattr(row, "float_shares", None)
            if prep_snapshot and prep_snapshot.float_shares is not None:
                float_shares = prep_snapshot.float_shares
            ind = SymbolIndicators(
                rvol=getattr(row, "rvol", None),
                float_shares=float_shares,
                ema50=prep_snapshot.levels.ema50 if prep_snapshot else None,
                ema200=prep_snapshot.levels.ema200 if prep_snapshot else None,
                vwap=prep_snapshot.levels.vwap_anchor if prep_snapshot else None,
            )
            symbols[symbol] = SymbolContext(
                symbol=symbol,
                timestamp=now,
                mode=mode,
                md=md,
                ind=ind,
                premarket_high=(
                    prep_snapshot.levels.prior_high if prep_snapshot else None
                ),
                premarket_low=(
                    prep_snapshot.levels.prior_low if prep_snapshot else None
                ),
                data_quality_flags=data_quality_flags,
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

    def _snapshot_watchlist(
        self,
        watchlist_symbols: List[str],
        watchlist_rows: List[object],
    ) -> Dict[str, MarketSnapshot]:
        """Batch snapshots for the watchlist; this is the orchestrator handoff point."""
        if not watchlist_symbols:
            return {}
        snapshots: Dict[str, MarketSnapshot] = {}
        failures: List[str] = []
        if self.market_data_hub is None:
            now_utc = datetime.now(timezone.utc)
            row_lookup = {
                getattr(row, "symbol", ""): row for row in watchlist_rows if getattr(row, "symbol", None)
            }
            for symbol in watchlist_symbols:
                row = row_lookup.get(symbol)
                if row is None:
                    failures.append(symbol)
                    continue
                snapshots[symbol] = MarketSnapshot(
                    symbol=symbol,
                    bid=getattr(row, "bid", None),
                    ask=getattr(row, "ask", None),
                    last=getattr(row, "last_price", None),
                    volume=getattr(row, "volume", None),
                    asof_utc=now_utc,
                    source="SCANNER_SNAPSHOT",
                    market_data_type="MOCK",
                )
            print("[ORCH][SNAPSHOT] MarketDataHub unavailable; using scanner rows")
        else:
            self.market_data_hub.reset_cycle()
            for symbol in watchlist_symbols:
                try:
                    observation = self.market_data_hub.snapshot(
                        symbol, request_source="Orchestrator"
                    )
                    snapshots[symbol] = observation.snapshot
                except Exception as exc:
                    failures.append(symbol)
                    print(f"[ORCH][SNAPSHOT][WARN] symbol={symbol} err={exc}")
        print(
            "ORCHESTRATOR_SNAPSHOT_BATCH completed "
            f"for K={len(watchlist_symbols)} success={len(snapshots)} failed={len(failures)}"
        )
        return snapshots

    @staticmethod
    def _symbols_from_candidates(candidates: List[object]) -> List[str]:
        symbols: List[str] = []
        for candidate in candidates or []:
            symbol = None
            if isinstance(candidate, str):
                symbol = candidate
            elif isinstance(candidate, dict):
                symbol = candidate.get("symbol")
            else:
                symbol = getattr(candidate, "symbol", None)
            if symbol:
                symbols.append(symbol)
        return symbols

    @staticmethod
    def _cap_list(items: List[str], limit: int) -> List[str]:
        if len(items) > limit:
            return items[:limit] + ["..."]
        return items

    def _ensure_cycle_id(self) -> str:
        if not self._current_cycle_id:
            self._current_cycle_id = str(uuid4())
        return self._current_cycle_id

    def _trace_event(self, stage: str, payload: dict, summary: Optional[str] = None) -> None:
        cycle_id = self._ensure_cycle_id()
        self.trace_bus.trace_event(
            stage,
            payload,
            cycle_id=cycle_id,
            run_mode=self.run_mode.value,
            strategy=self.selected_strategy_key,
            summary=summary,
        )

    def _emit_market_session_state(self, session: str, now: datetime | None = None) -> None:
        if session == self._last_market_session:
            return
        timestamp = now or datetime.now(timezone.utc)
        ny_time = to_ny_time(timestamp)
        payload = {
            "session": session,
            "previous_session": self._last_market_session,
            "timestamp_utc": timestamp.isoformat(),
            "ny_time": ny_time.isoformat(),
        }
        self.event_collector.emit(
            event_type="MARKET_SESSION_STATE",
            source="SystemConfig",
            payload=payload,
        )
        self._trace_event("MARKET_SESSION", payload)
        self._last_market_session = session

    def _trace_halt(
        self,
        *,
        reason_code: str,
        message: str,
        stage: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        payload = {
            "reason_code": reason_code,
            "message": message,
            "stage": stage,
            "details": details or {},
        }
        self._last_halt_reason = payload
        self._trace_event("HALT", payload)

    def _selection_spec_summary(self, policy: StockSelectionPolicy) -> dict:
        base = StockSelectionSpec()
        relaxed_gates: list[str] = []
        if policy.gap_min_pct < base.gap_min_pct:
            relaxed_gates.append("gap_min_pct")
        if policy.rvol_min < base.rvol_min:
            relaxed_gates.append("rvol_min")
        if policy.float_max_millions > base.float_max_millions:
            relaxed_gates.append("float_max_millions")
        if policy.min_volume < base.min_volume:
            relaxed_gates.append("min_volume")
        if policy.min_premarket_volume < base.min_premarket_volume:
            relaxed_gates.append("min_premarket_volume")
        if policy.require_catalyst is False and base.require_catalyst:
            relaxed_gates.append("require_catalyst")
        if policy.price_max > base.price_max:
            relaxed_gates.append("price_max")
        return {
            "policy_name": policy.policy_name,
            "top_gainers_n": policy.top_gainers_n,
            "max_symbols_per_cycle": policy.max_symbols_per_cycle,
            "session_allowlist": list(policy.session_allowlist),
            "relaxed_gates": relaxed_gates,
        }

    def replay_events(self, events):
        self.replay_engine.replay(events)

    def replay_cycle_events(self):
        print("[REPLAY] Initiating cycle-scoped replay")
        self.replay_events(self.event_collector.snapshot_cycle())

    def replay_all_events(self):
        print("[REPLAY] Initiating full-run replay")
        self.replay_events(self.event_collector.snapshot_all())

    def _check_daily_loss_limits(self, ny_date: str) -> None:
        if self.run_mode not in {RunMode.PAPER, RunMode.LIVE}:
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
            self._trace_halt(
                reason_code="STOP_REQUESTED",
                message=f"Stop requested at stage boundary {stage_label}",
                stage=stage_label,
                details={"mode": mode.value},
            )
            return True
        if self._halted:
            print(
                f"[STOP] Orchestrator halted prior to stage '{stage_label}' "
                "— exiting cycle safely."
            )
            self._trace_halt(
                reason_code="HALTED",
                message=f"Orchestrator halted prior to stage {stage_label}",
                stage=stage_label,
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
        retry_count = 0
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
                self._emit_market_session_state(current_session)
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
                        "[GATE] Teaching note: PAPER would still run for education, "
                        "but LIVE waits for an open session."
                    )
                    if max_cycles is not None:
                        cycles_run += 1
                        if cycles_run >= max_cycles:
                            break
                else:
                    print(
                        "[SAFETY] RUN_MODE and session allow safe progression to orchestrator.run_once()."
                    )
                    should_continue = self.run_once()
                    cycles_run += 1
                    retry_count = 0
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
            except (ProviderConnectionError, ConnectionError, TimeoutError) as exc:
                retry_count += 1
                self._degraded = True
                backoff_seconds = min(60, max(1, int(2 ** (retry_count - 1))))
                next_attempt = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                if max_cycles is not None:
                    print(
                        "[CONNECTIVITY] "
                        "Max cycles set; aborting after connectivity error."
                    )
                    if not self.stop_controller.is_stop_requested():
                        self._request_stop(
                            StopMode.GRACEFUL,
                            reason="Connectivity error with max_cycles",
                            source="CoreOrchestrator",
                        )
                    self._shutdown(self.stop_controller.stop_mode() or StopMode.GRACEFUL)
                    performed_shutdown = True
                    break
                print(
                    "[CONNECTIVITY] "
                    f"STATE=DEGRADED retry={retry_count} backoff={backoff_seconds}s "
                    f"next_attempt={next_attempt.isoformat()}"
                )
                self._trace_halt(
                    reason_code="CONNECTIVITY_RETRY",
                    message=str(exc),
                    stage="CONNECTIVITY",
                    details={
                        "retry": retry_count,
                        "backoff_seconds": backoff_seconds,
                        "next_attempt": next_attempt.isoformat(),
                    },
                )
                time.sleep(backoff_seconds)
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
        except ProviderConnectionError:
            raise
        except SystemExit:
            raise
        except Exception as exc:
            return self._handle_fault(exc)

    def _run_once_inner(self) -> bool:
        print("[INFO] Starting orchestrator cycle (teaching-only).")
        self._current_cycle_id = str(uuid4())
        self._last_halt_reason = None
        cycle_started_at = datetime.now(timezone.utc)
        ny_time = to_ny_time(cycle_started_at)
        uk_time = to_uk_time(cycle_started_at)
        session_override = str(get_config("SESSION_PHASE_OVERRIDE") or "").strip().upper()
        session_phase = session_override or market_session_phase(cycle_started_at)
        print(
            "[SESSION] "
            f"phase={session_phase} ny_time={ny_time.isoformat()} "
            f"uk_time={uk_time.isoformat()} utc={cycle_started_at.isoformat()}"
        )
        return self._run_manager_pipeline(
            cycle_started_at=cycle_started_at,
            ny_time=ny_time,
            uk_time=uk_time,
            session_phase=session_phase,
        )

    def _run_manager_pipeline(
        self,
        *,
        cycle_started_at: datetime,
        ny_time: datetime,
        uk_time: datetime,
        session_phase: str,
    ) -> bool:
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        mode_manager = self.runtime_mode_manager
        print(f"[RUNTIME] {mode_manager.describe()}")
        strategy_policy, scanner_policy = self._build_scanner_policy(session_phase)
        scanner_request = self._build_scanner_request(
            scanner_policy,
            strategy_name=self.selected_strategy_key,
            session_phase=session_phase,
        )
        force_mock_provider = False
        try:
            self.connection_manager.ensure_connected()
        except Exception as exc:
            print("STATE=DEGRADED")
            print(f"[CONNECTIVITY] IBKR connection failed: {exc}")
            self._trace_halt(
                reason_code="CONNECTIVITY_FAILURE",
                message=str(exc),
                stage="CONNECTIVITY",
            )
            fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
            force_mock_provider = (
                fallback_enabled
                or self.run_mode == RunMode.PAPER
                or str(get_config("SCANNER_DATA_SOURCE") or "").upper() == "MOCK"
            )
        if self.market_data_snapshot_manager is None:
            self.market_data_snapshot_manager = MarketDataSnapshotManager(
                self.connection_manager.optional_client
            )
        provider_override = MockScannerProvider() if force_mock_provider else None
        scanner_payload = run_scanner_cycle(
            mode="integrated",
            policy=scanner_policy,
            scanner_request=scanner_request,
            event_collector=self.event_collector,
            provider=provider_override,
            market_data_client=self.connection_manager.optional_client,
            disconnect_provider=provider_override is not None,
        )
        observations = list(scanner_payload.get("candidate_metrics", []))
        universe_entries = list(scanner_payload.get("universe_top_n", []))
        universe_symbols = [
            entry.get("symbol") for entry in universe_entries if isinstance(entry, dict)
        ]
        selection_spec_summary = self._selection_spec_summary(scanner_policy)
        self._trace_event(
            "UNIVERSE",
            {
                "selection_spec": selection_spec_summary,
                "scan_request": {
                    "universe_source": scanner_request.universe_source.value,
                    "scan_code": scanner_request.ibkr_scan_code,
                    "requested_top_n": scanner_request.requested_top_n,
                },
                "universe": universe_entries,
            },
            summary=(
                "top_n="
                f"{len(universe_entries)} symbols={self._cap_list(universe_symbols, 50)}"
            ),
        )
        self.scanner_diagnostics_manager.print_top_50(observations)
        watchlist = list(scanner_payload.get("watchlist_k", []))
        if not watchlist:
            selector = resolve_watchlist_selector(scanner_policy.ranking_intent)
            if selector is not None:
                # Strategy-owned ranking authority for Ross Momentum.
                watchlist = selector(observations, scanner_policy)
            else:
                watchlist = self._select_watchlist_for_policy(
                    observations,
                    scanner_policy,
                    enforce_session_allowlist=False,
                )
        self.scanner_diagnostics_manager.print_watchlist(watchlist, observations)
        watchlist_symbols = [row.symbol for row in watchlist if row.symbol]
        focus_rows = list(scanner_payload.get("focus_m", []))
        if not focus_rows:
            focus_limit = int(scanner_policy.focus_limit_m)
            focus_rows = watchlist[:focus_limit] if focus_limit > 0 else []
        focus_symbols = [row.symbol for row in focus_rows if row.symbol]
        self._trace_event(
            "WATCHLIST",
            {
                "selection_spec": selection_spec_summary,
                "watchlist_symbols": watchlist_symbols,
            },
            summary=(
                "watchlist="
                f"{len(watchlist_symbols)} symbols={self._cap_list(watchlist_symbols, 15)}"
            ),
        )
        self._trace_event(
            "FOCUS",
            {
                "selection_spec": selection_spec_summary,
                "focus_symbols": focus_symbols,
            },
            summary=(
                "focus="
                f"{len(focus_symbols)} symbols={self._cap_list(focus_symbols, 5)}"
            ),
        )
        if watchlist_symbols:
            print(
                f"[WATCHLIST] size={len(watchlist_symbols)} symbols={watchlist_symbols}"
            )
        else:
            print("[WATCHLIST] empty watchlist accepted")
        snapshots_by_symbol, snapshot_quality = self.market_data_snapshot_manager.batch_snapshots(
            watchlist_symbols
        )
        timestamp_utc = scanner_payload.get("timestamp_utc") or datetime.now(
            timezone.utc
        ).isoformat()
        session_label = normalize_session_label(
            (watchlist[0].session_label if watchlist else session_phase)
        )
        self.strategy_runner.receive_watchlist_snapshot(
            watchlist_symbols=watchlist_symbols,
            snapshots=snapshots_by_symbol,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
        )
        strategy_watchlist = watchlist
        if self.selected_strategy_key == "statistical_intraday_momentum":
            strategy_watchlist = focus_rows
            print(
                "[STRATEGY][FOCUS] "
                f"statistical_intraday_momentum using focus_m={len(focus_rows)}"
            )
        strategy_output = self.strategy_runner.process(
            strategy_key=self.selected_strategy_key,
            watchlist=strategy_watchlist,
            snapshots=snapshots_by_symbol,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
            mode=self.run_mode,
            session_phase=session_phase,
        )
        if self.regime_layer.enabled:
            self.regime_layer.evaluate(
                candidates=scanner_payload.get("candidates", []),
                session=get_current_market_session(),
            )
        diagnostics = scanner_payload.get("diagnostics", {})
        provider_error = diagnostics.get("provider_error")
        provider_fallback = diagnostics.get("provider_fallback")
        if provider_error or provider_fallback:
            message = f"provider_error={provider_error} provider_fallback={provider_fallback}"
            print(f"[CONNECTIVITY] STATE=DEGRADED {message}")
            self._trace_halt(
                reason_code="SCANNER_CONNECTIVITY",
                message=message,
                stage="SCANNER",
            )
        if mode_manager.allow_orders:
            print("[EXECUTION] Orders allowed — execution path enabled (dry-run).")
        else:
            print("[EXECUTION] dry-run (orders disabled by mode)")
        self._trace_event(
            "ACTION",
            {
                "trade_intents": len(strategy_output or []),
                "allow_orders": mode_manager.allow_orders,
            },
            summary=f"intents={len(strategy_output or [])}",
        )
        if snapshot_quality:
            missing = {
                symbol: quality.missing_fields
                for symbol, quality in snapshot_quality.items()
                if quality.missing_fields
            }
            if missing:
                print(
                    "[SNAPSHOT][SUMMARY] missing_required_fields="
                    f"{missing}"
                )
        if not strategy_output:
            print("[STRATEGY] No trade intents generated.")
        return True

    @staticmethod
    def _select_watchlist_for_policy(
        observations: list[CandidateMetrics],
        scanner_policy: StockSelectionPolicy,
        *,
        enforce_session_allowlist: bool = True,
    ) -> list[CandidateMetrics]:
        session_allowlist = {session.upper() for session in scanner_policy.session_allowlist}
        eligible = []
        for observation in observations:
            session_label = (observation.session_label or "").upper()
            if (
                enforce_session_allowlist
                and session_allowlist
                and session_label
                and session_label not in session_allowlist
            ):
                continue
            gate_checks = observation.gate_checks or {}
            if any(not passed for passed in gate_checks.values()):
                continue
            eligible.append(observation)
        ranked = sorted(
            eligible,
            key=lambda row: (
                row.rank_score or 0.0,
                row.pct_change or 0.0,
                row.dollar_volume or 0.0,
            ),
            reverse=True,
        )
        watchlist_limit = int(scanner_policy.watchlist_limit_k)
        if watchlist_limit <= 0:
            return []
        return ranked[:watchlist_limit]
        strategy_policy, scanner_policy = self._build_scanner_policy(session_phase)
        selection_spec_summary = self._selection_spec_summary(scanner_policy)
        scanner_request = self._build_scanner_request(
            scanner_policy,
            strategy_name=self.selected_strategy_key,
            session_phase=session_phase,
        )
        execution_intent = build_execution_intent(
            strategy_name=strategy_policy.name,
            mode=self.run_mode.value,
            session_phase=session_phase,
            policy=scanner_policy,
            execution_enabled=self.execution_enabled,
        )
        print(
            f"[ORCH][POLICY] loaded strategy={strategy_policy.name} "
            f"version={strategy_policy.version} policy={strategy_policy.name} "
            "stock_selection=ENABLED"
        )
        print(
            "[ORCH][POLICY] stock_selection_spec="
            f"{json.dumps(asdict(scanner_policy), sort_keys=True)}"
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
            scanner_watchlist_payload = run_scanner_cycle(
                mode="integrated",
                policy=scanner_policy,
                scanner_request=scanner_request,
                event_collector=self.event_collector,
            )
        except ProviderConnectionError as exc:
            self._trace_halt(
                reason_code="SCANNER_CONNECTIVITY",
                message=str(exc),
                stage="SCANNER",
            )
            raise
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="SCANNER",
                stage_exception=exc,
            )
            self._trace_halt(
                reason_code="SCANNER_EXCEPTION",
                message=str(exc),
                stage="SCANNER",
            )
            return False
        universe_entries = list(scanner_watchlist_payload.get("universe_top_n", []))
        candidate_metrics = list(scanner_watchlist_payload.get("candidate_metrics", []))
        metrics_by_symbol = {row.symbol: row for row in candidate_metrics}
        enriched_universe = []
        for entry in universe_entries:
            symbol = entry.get("symbol") if isinstance(entry, dict) else getattr(entry, "symbol", None)
            if not symbol:
                continue
            metrics = metrics_by_symbol.get(symbol)
            enriched_universe.append(
                {
                    "symbol": symbol,
                    "rank": entry.get("rank") if isinstance(entry, dict) else getattr(entry, "rank", None),
                    "last_price": getattr(metrics, "last_price", None),
                    "gap_pct": getattr(metrics, "gap_pct", None),
                    "pct_change": getattr(metrics, "pct_change", None),
                    "rvol": getattr(metrics, "rvol", None),
                    "volume": getattr(metrics, "volume", None),
                    "spread_pct": getattr(metrics, "spread_pct", None),
                }
            )
        universe_symbols = [entry.get("symbol") for entry in enriched_universe]
        self._trace_event(
            "UNIVERSE",
            {
                "selection_spec": selection_spec_summary,
                "scan_request": {
                    "universe_source": scanner_request.universe_source.value,
                    "scan_code": scanner_request.ibkr_scan_code,
                    "requested_top_n": scanner_request.requested_top_n,
                },
                "universe": enriched_universe,
            },
            summary=(
                "top_n="
                f"{len(enriched_universe)} symbols="
                f"{self._cap_list(universe_symbols, 50)}"
            ),
        )
        self.last_scanner_watchlist_payload = scanner_watchlist_payload
        scanner_results = list(scanner_watchlist_payload.get("candidates", []))
        self.event_collector.emit(
            event_type="SCANNER_WATCHLIST",
            source="Scanner",
            payload={
                "scanner_version": scanner_watchlist_payload.get("scanner_version"),
                "timestamp_utc": scanner_watchlist_payload.get("timestamp_utc"),
                "symbols": scanner_watchlist_payload.get("symbols", []),
            },
        )
        watchlist_k = list(scanner_watchlist_payload.get("watchlist_k", []))
        focus_m = list(scanner_watchlist_payload.get("focus_m", []))
        watchlist_symbols = list(scanner_watchlist_payload.get("watchlist_k_symbols", []))
        focus_symbols = list(scanner_watchlist_payload.get("focus_m_symbols", []))
        if not watchlist_symbols:
            watchlist_symbols = self._symbols_from_candidates(watchlist_k)
        if not focus_symbols:
            focus_symbols = self._symbols_from_candidates(focus_m)
        print(f"WATCHLIST_K_SELECTED (K={len(watchlist_symbols)}): {watchlist_symbols}")
        drop_reason_summary = scanner_watchlist_payload.get("drop_reason_summary", {})
        self._trace_event(
            "WATCHLIST",
            {
                "selection_spec": selection_spec_summary,
                "watchlist_symbols": watchlist_symbols,
                "drop_reason_summary": drop_reason_summary,
            },
            summary=(
                "watchlist="
                f"{len(watchlist_symbols)} symbols="
                f"{self._cap_list(watchlist_symbols, 15)} "
                f"drop_reasons={drop_reason_summary}"
            ),
        )
        prep_symbols: list[str] = []
        for entry in universe_entries:
            if isinstance(entry, dict):
                symbol = entry.get("symbol")
            else:
                symbol = getattr(entry, "symbol", None)
            if symbol:
                prep_symbols.append(symbol)
        if prep_symbols:
            last_price_by_symbol = {
                row.symbol: row.last_price
                for row in candidate_metrics
                if getattr(row, "symbol", None)
            }
            float_by_symbol = {
                row.symbol: row.float_shares
                for row in candidate_metrics
                if getattr(row, "symbol", None)
            }
            prior_close_by_symbol = {
                row.symbol: (row.prev_close or row.ref_close_rth)
                for row in candidate_metrics
                if getattr(row, "symbol", None)
            }
            gap_pct_by_symbol = {
                row.symbol: row.gap_pct
                for row in candidate_metrics
                if getattr(row, "symbol", None)
            }
            self.prep_engine.update_from_universe(
                prep_symbols,
                last_price_by_symbol=last_price_by_symbol,
                float_by_symbol=float_by_symbol,
                prior_close_by_symbol=prior_close_by_symbol,
                gap_pct_by_symbol=gap_pct_by_symbol,
                reason="SCANNER_UNIVERSE_SNAPSHOT",
            )
        try:
            stored = self.storage_engine.store_watchlist(
                strategy_name=str(scanner_policy.policy_name),
                session_phase=session_phase,
                watchlist_symbols=watchlist_symbols,
                focus_symbols=focus_symbols,
                metrics_payload={
                    "watchlist_rows": scanner_watchlist_payload.get("watchlist_rows", []),
                    "focus_rows": scanner_watchlist_payload.get("focus_rows", []),
                    "drop_reason_summary": drop_reason_summary,
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
        self._evaluate_runtime_safety(
            cycle_stage="SCANNER",
            stage_exception=None,
            scanner_results=scanner_results,
        )
        diagnostics = scanner_watchlist_payload.get("diagnostics", {})
        provider_source = diagnostics.get("provider_source")
        provider_error = diagnostics.get("provider_error")
        provider_fallback = diagnostics.get("provider_fallback")
        data_quality_flags = scanner_watchlist_payload.get("data_quality_by_symbol", {})
        auto_lockdown_enabled = bool(get_config("IBKR_AUTO_LOCKDOWN_ENABLED"))
        if self.run_mode in {RunMode.READ_ONLY, RunMode.LIVE, RunMode.PAPER}:
            if provider_error or provider_fallback or provider_source == "MOCK":
                message = (
                    "IBKR connectivity degraded "
                    f"source={provider_source} error={provider_error} fallback={provider_fallback}"
                )
                print(f"[CONNECTIVITY] {message}")
                self._degraded = True
                if self.run_mode == RunMode.LIVE:
                    self._trace_halt(
                        reason_code="IBKR_CONNECTIVITY",
                        message=message,
                        stage="SCANNER",
                        details={
                            "provider_source": provider_source,
                            "provider_error": provider_error,
                            "provider_fallback": provider_fallback,
                        },
                    )
                    raise ProviderConnectionError(message)
            if data_quality_flags:
                print(
                    "[DATA_QUALITY] Flags detected in live scan "
                    f"symbols={list(data_quality_flags.keys())}"
                )
                if auto_lockdown_enabled:
                    self._request_stop(
                        StopMode.PANIC,
                        reason="Data quality degradation detected",
                        source="Scanner",
                    )
                    self._trace_halt(
                        reason_code="DATA_QUALITY_LOCKDOWN",
                        message="Data quality degradation detected",
                        stage="SCANNER",
                        details={"symbols": list(data_quality_flags.keys())},
                    )
                    return False
                self._degraded = True
        if self._stop_requested_at_boundary("SCANNER"):
            return False
        watchlist_rows = list(scanner_watchlist_payload.get("watchlist_rows", []))
        # Orchestrator snapshot batch occurs here (post-watchlist gate).
        snapshots_by_symbol = self._snapshot_watchlist(
            watchlist_symbols=watchlist_symbols,
            watchlist_rows=watchlist_rows,
        )
        session_label = normalize_session_label(
            (getattr(watchlist_rows[0], "session", "") if watchlist_rows else session_phase)
        )
        timestamp_utc = scanner_watchlist_payload.get("timestamp_utc") or datetime.now(
            timezone.utc
        ).isoformat()
        self.strategy_runner.receive_watchlist_snapshot(
            watchlist_symbols=watchlist_symbols,
            snapshots=snapshots_by_symbol,
            session_label=session_label,
            timestamp_utc=timestamp_utc,
        )
        strategy_context = self._build_strategy_context(
            now=cycle_started_at,
            ny_time=ny_time,
            uk_time=uk_time,
            session_phase=session_phase,
            watchlist_rows=watchlist_rows,
            watchlist_k=watchlist_k,
            focus_m=focus_m,
            snapshots_by_symbol=snapshots_by_symbol,
        )
        print(
            "[ORCH][CTX] "
            f"watchlist_k={len(strategy_context.watchlist_k)} "
            f"focus_m={len(strategy_context.focus_m)} "
            f"symbols_in_context={len(strategy_context.symbols)}"
        )
        focus_payload = []
        for candidate in strategy_context.focus_m:
            focus_payload.append(
                {
                    "symbol": candidate.symbol,
                    "gap_pct": candidate.gap_pct,
                    "pct_change": candidate.pct_change,
                    "rvol": candidate.rvol,
                    "dollar_volume": candidate.dollar_volume,
                    "rank_score": candidate.rank_score,
                }
            )
        focus_symbols_set = {entry["symbol"] for entry in focus_payload}
        rejected_payload = []
        for candidate in candidate_metrics:
            if candidate.symbol in focus_symbols_set:
                continue
            reasons = list(candidate.drop_reasons or [])
            rejected_payload.append(
                {
                    "symbol": candidate.symbol,
                    "reasons": reasons[:2],
                }
            )
        self._trace_event(
            "FOCUS",
            {
                "selection_spec": selection_spec_summary,
                "strategy_policy": strategy_policy.name,
                "focus": focus_payload,
                "rejected": rejected_payload,
            },
            summary=(
                "focus="
                f"{len(focus_payload)} symbols={self._cap_list(list(focus_symbols_set), 5)}"
            ),
        )
        focus_set = set(self._symbols_from_candidates(strategy_context.focus_m))
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

        pattern_results = []
        signals = []
        if self.selected_strategy_key == "statistical_intraday_momentum":
            print(
                "[TEACH] >>> Pattern stage skipped — statistical strategy does not use Ross patterns."
            )
            print(
                "[TEACH] >>> Signals stage skipped — statistical strategy uses statistical signals."
            )
        else:
            print("[TEACH] >>> Pattern stage — evaluate shapes/behaviors (conceptual).")
            try:
                pattern_results = self.pattern_engine.evaluate_patterns(scanner_results or [])
            except Exception as exc:
                self._evaluate_runtime_safety(
                    cycle_stage="PATTERN",
                    stage_exception=exc,
                    scanner_results=scanner_results,
                )
                self._trace_halt(
                    reason_code="PATTERN_EXCEPTION",
                    message=str(exc),
                    stage="PATTERN",
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
            if self.selected_strategy_key == "statistical_intraday_momentum":
                interface_intents = []
                interface_event = self.event_collector.emit(
                    event_type="STRATEGY_INTERFACE_INTENTS",
                    source="StatisticalIntradayMomentum",
                    payload={"count": len(interface_intents)},
                )
            else:
                interface_intents = ross_trade_intents_to_decision_intents(strategy_output)
                interface_event = self.event_collector.emit(
                    event_type="STRATEGY_INTERFACE_INTENTS",
                    source="RossMomentumAdapter",
                    payload={"count": len(interface_intents)},
                )
            print(interface_event)
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="STRATEGY",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
            )
            self._trace_halt(
                reason_code="STRATEGY_EXCEPTION",
                message=str(exc),
                stage="STRATEGY",
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
            e22_config = E22PolicyConfig(
                enabled=bool(get_config("E22_STRATEGY_SCALABILITY_ENABLED")),
                max_strategies_per_cycle=int(get_config("E22_MAX_STRATEGIES_PER_CYCLE")),
                max_intents_per_cycle=int(get_config("E22_MAX_INTENTS_PER_CYCLE")),
                max_positions_per_cycle=int(get_config("E22_MAX_POSITIONS_PER_CYCLE")),
                symbol_exclusivity=bool(get_config("E22_SYMBOL_EXCLUSIVITY")),
                strategy_priority=dict(get_config("E22_STRATEGY_PRIORITY") or {}),
                strategy_max_intents=dict(get_config("E22_STRATEGY_MAX_INTENTS") or {}),
            )
            strategy_output, e22_artifact = apply_e22_arbitration_layer(strategy_output, e22_config)
            if e22_artifact is not None:
                self.event_collector.emit(
                    event_type="E22_ARBITRATION",
                    source="E22IntentArbitrator",
                    payload={
                        "allowed_count": len(e22_artifact.allowed_intents),
                        "suppressed_count": len(e22_artifact.suppressed_intents),
                        "suppression_counts_by_reason_code": e22_artifact.suppression_counts_by_reason_code,
                        "strategy_order": e22_artifact.strategy_order,
                        "policy": e22_artifact.policy,
                    },
                )
        except Exception as exc:
            self._evaluate_runtime_safety(
                cycle_stage="INTENT_NORMALISATION",
                stage_exception=exc,
                scanner_results=scanner_results,
                pattern_results=pattern_results,
                strategy_output=strategy_output,
            )
            self._trace_halt(
                reason_code="INTENT_NORMALISATION_EXCEPTION",
                message=str(exc),
                stage="INTENT_NORMALISATION",
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

        decision_output = []
        if strategy_output:
            decision_timestamp = datetime.now(timezone.utc).isoformat()
            decision_artifact = build_decision_artifact(
                strategy_name=self.selected_strategy_key,
                run_mode=self.run_mode.value,
                session_phase=execution_intent.session_phase,
                intents=strategy_output,
                source="CoreOrchestrator",
                created_at=decision_timestamp,
                metadata={"tick": tick, "cycle_id": self._ensure_cycle_id()},
            )
            decision_output.append(decision_artifact)
            for trade_intent in strategy_output:
                trade_intent.decision_id = decision_artifact.decision_id
            self.event_collector.emit(
                event_type="DECISION_ARTIFACT_CREATED",
                source="CoreOrchestrator",
                payload={
                    "decision_id": decision_artifact.decision_id,
                    "strategy_name": decision_artifact.strategy_name,
                    "intent_count": len(decision_artifact.intents),
                    "run_mode": decision_artifact.run_mode,
                    "session_phase": decision_artifact.session_phase,
                    "created_at": decision_artifact.created_at,
                },
            )
            self._trace_event(
                "DECISION",
                {
                    "decision_id": decision_artifact.decision_id,
                    "strategy_name": decision_artifact.strategy_name,
                    "intent_count": len(decision_artifact.intents),
                    "run_mode": decision_artifact.run_mode,
                    "session_phase": decision_artifact.session_phase,
                    "created_at": decision_artifact.created_at,
                },
                summary=f"decision_id={decision_artifact.decision_id} intents={len(decision_artifact.intents)}",
            )

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
                self._trace_halt(
                    reason_code="RISK_EXCEPTION",
                    message=str(exc),
                    stage="RISK",
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
                        self._trace_halt(
                            reason_code="EXECUTION_EXCEPTION",
                            message=str(exc),
                            stage="EXECUTION",
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
        orders_payload = [
            {
                "symbol": result.symbol,
                "side": result.direction,
                "qty": result.quantity,
                "order_type": "MKT",
                "status": result.status,
            }
            for result in execution_output
            if getattr(result, "attempted", False)
        ]
        if self.run_mode == RunMode.READ_ONLY:
            action_label = "READONLY_NO_ORDERS"
            action_reason = "READONLY mode blocks order routing"
        elif execution_intent.scan_only:
            action_label = "SCAN_ONLY"
            action_reason = "Execution intent set to scan_only"
        elif not self.execution_enabled:
            action_label = "EXECUTION_DISABLED"
            action_reason = "Execution disabled"
        elif orders_payload:
            action_label = "ORDERS_PLACED"
            action_reason = "Orders routed to execution engine"
        else:
            action_label = "NO_ORDERS"
            action_reason = "No eligible orders to place"
        self._trace_event(
            "ACTION",
            {
                "action": action_label,
                "reason": action_reason,
                "orders": orders_payload,
            },
            summary=f"action={action_label} orders={len(orders_payload)}",
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
            self._trace_halt(
                reason_code="EXIT_SIGNALS_EXCEPTION",
                message=str(exc),
                stage="EXIT_SIGNALS",
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
            self._trace_halt(
                reason_code="TRADE_EXIT_EXCEPTION",
                message=str(exc),
                stage="TRADE_EXIT",
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
                decision_output=decision_output or [],
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
            self._trace_halt(
                reason_code="STORAGE_RECORD_EXCEPTION",
                message=str(exc),
                stage="STORAGE",
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
            self._trace_halt(
                reason_code="STORAGE_PERSIST_EXCEPTION",
                message=str(exc),
                stage="STORAGE",
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
            self._trace_halt(
                reason_code="INVARIANT_FAILURE",
                message=str(exc),
                stage="INVARIANTS",
            )
            return False
        print(
            f"[REPLAY] Replay selection — mode={self.replay_mode.value} "
            f"run_mode={run_mode_value}"
        )
        if self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY}:
            print(
                "[REPLAY] Replay is locked down in LIVE/READ_ONLY — skipping replay"
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
        print(f"[VALIDATION] Scanner mode resolved: {self.scanner_mode}")
        print(f"[VALIDATION] Scanner data source: {get_config('SCANNER_DATA_SOURCE')}")
        if self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY, RunMode.PAPER}:
            market_data_source = "IBKR"
            if self.run_mode == RunMode.READ_ONLY and self.market_data_hub is None:
                market_data_source = "MOCK_FALLBACK"
        else:
            market_data_source = "MOCK"
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
        if market_data_source == "IBKR":
            print("[VALIDATION] MARKET DATA: LIVE IBKR")
        broker_adapter = getattr(self.execution_engine, "broker", None)
        broker_name = (
            broker_adapter.name()
            if broker_adapter is not None and hasattr(broker_adapter, "name")
            else type(broker_adapter).__name__ if broker_adapter is not None else "NONE"
        )
        print(f"[VALIDATION] Broker adapter in use: {broker_name}")
        if self.run_mode == RunMode.READ_ONLY:
            if market_data_source == "MOCK_FALLBACK":
                print("[VALIDATION][WARN] READ_ONLY using MOCK fallback market data.")
            elif "MOCK" in market_data_source:
                raise RuntimeError(
                    "Market data source resolved to MOCK under READ_ONLY conditions."
                )
            if isinstance(broker_adapter, SimBroker):
                raise RuntimeError("SimBroker instantiated under READ_ONLY conditions.")
        if self.run_mode == RunMode.READ_ONLY:
            print("[VALIDATION] READ_ONLY: live data enabled")
            print("[VALIDATION] READ_ONLY: execution disabled by design")
            if self.market_data_hub is None:
                print(
                    "[VALIDATION][WARN] READ_ONLY fallback active: "
                    "MarketDataHub unavailable."
                )
            elif not isinstance(self.price_feed, MarketDataPriceFeed):
                raise RuntimeError("READ_ONLY must use MarketDataPriceFeed")
        if self.storage_engine.enabled and self.storage_engine.backend == "sqlite":
            if self.storage_engine._store is None:
                raise RuntimeError("Storage engine failed to open SQLite store")
            print("[VALIDATION] Storage OK — SQLite opened")

    def _resolve_market_data_status(self) -> tuple[str, bool]:
        if self.scanner_mode == "TEACHING" or self.run_mode in {RunMode.SIM, RunMode.PAPER}:
            return "N/A", True
        diagnostics = self.last_scanner_watchlist_payload.get("diagnostics", {})
        provider_source = diagnostics.get("provider_source")
        provider_error = diagnostics.get("provider_error")
        provider_fallback = diagnostics.get("provider_fallback")
        if provider_error or provider_fallback:
            return "DEGRADED", True
        if provider_source == "MOCK":
            return "DEGRADED", True
        if provider_source:
            return "OK", True
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
            self._trace_halt(
                reason_code="FAULT_RETRY_NOT_IMPLEMENTED",
                message=fault.message,
                stage="FAULT",
            )
            return False
        if action == RecoveryAction.SKIP_STAGE:
            print("[FAULT] Action=SKIP_STAGE — skipping stage not implemented; aborting cycle.")
            self._trace_halt(
                reason_code="FAULT_SKIP_STAGE_NOT_IMPLEMENTED",
                message=fault.message,
                stage="FAULT",
            )
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
            self._trace_halt(
                reason_code="FAULT_ABORT_CYCLE",
                message=fault.message,
                stage="FAULT",
            )
            return False
        if action == RecoveryAction.HALT_SYSTEM:
            print("[FAULT] Action=HALT_SYSTEM — halting orchestrator safely.")
            mode = (
                StopMode.PANIC
                if self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY}
                else StopMode.GRACEFUL
            )
            self._request_stop(
                mode,
                reason=f"Fault: {fault.message}",
                source="FaultRecovery",
            )
            self._trace_halt(
                reason_code="FAULT_HALT_SYSTEM",
                message=fault.message,
                stage="FAULT",
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
        watchlist = list(self.last_scanner_watchlist_payload.get("watchlist_k_symbols", []))
        focus = list(self.last_scanner_watchlist_payload.get("focus_m_symbols", []))
        if not watchlist:
            watchlist = self._symbols_from_candidates(
                list(self.last_scanner_watchlist_payload.get("watchlist_k", []))
            )
        if not focus:
            focus = self._symbols_from_candidates(
                list(self.last_scanner_watchlist_payload.get("focus_m", []))
            )
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
        In PAPER, violations raise an exception for visibility.
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
            self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY}
            and self.replay_mode != EventReplayMode.OFF
        ):
            violations.append("Replay requested while in LIVE/READ_ONLY mode")
        current_mode = get_run_mode()
        if current_mode != self.run_mode:
            violations.append(
                "Run mode drift detected "
                f"(resolved={self.run_mode.value} current={current_mode.value})"
            )
        if self.run_mode == RunMode.LIVE and isinstance(
            self.sim_clock, SimClock
        ):
            violations.append("Deterministic SimClock detected in LIVE mode")
        if self.run_mode == RunMode.LIVE and isinstance(
            self.price_feed, DeterministicPriceFeed
        ):
            print(
                "[SAFETY][WARN] Deterministic price feed detected in LIVE; "
                "continuing in degraded mode."
            )
            self._degraded = True

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

        if self.run_mode in {RunMode.LIVE, RunMode.READ_ONLY}:
            print(
                "[SAFETY] LIVE/READ_ONLY mode violation — entering deterministic safe halt."
            )
            self._trace_halt(
                reason_code="RUNTIME_SAFETY_VIOLATION",
                message="; ".join(violations),
                stage=stage_label,
            )
            self._request_stop(
                StopMode.PANIC,
                reason="Runtime safety violation",
                source="RuntimeSafety",
            )
            return

        raise RuntimeSafetyError("; ".join(violations))
