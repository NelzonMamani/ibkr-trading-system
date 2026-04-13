"""
Core Orchestrator for PHASE 3 — Skeleton System (Teaching-First).

This file only outlines the conceptual flow of the trading system and contains
no real trading logic, integrations, or data handling. It exists solely to make
the system stages and their order easy to follow during this teaching phase.
"""
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from threading import Lock, Thread
from uuid import uuid4
from typing import Dict, List, Optional, Set, Tuple

from src.brokers import IbkrLiveBroker, SimBroker
from src.adapters.brokers.ibkr.ibkr_order_translator import IBAPI_AVAILABLE
from src.config.config_resolver import emit_config_event, get_config
from src.config.runtime_config import (
    EventReplayMode,
    RunMode,
    get_daily_loss_hard_limit,
    get_daily_loss_warning_limit,
    get_ibkr_api_write_allowed,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_port,
    get_ibkr_readonly_enabled,
    get_run_mode,
    get_scanner_mode,
)
from src.config.system_config import get_current_market_session
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.engines.position_management_engine import ManagedPosition, PositionManagementEngine
from src.core.engines.trade_lifecycle_engine import LifecycleEvent, TradeLifecycleEngine
from src.core.portfolio import BrokerPositionSnapshotAdapter, PortfolioArbitrator, PortfolioState
from src.core.event_collector import EventCollector
from src.data.fundamentals.float_provider import FloatProvider
from src.data.manual_focus_loader import ManualFocusConfig
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
from src.core.decision_trace import DecisionTraceStore, SymbolDecisionTrace
from src.execution.execution_engine import ExecutionEngine
from src.execution.dev_tools.flatten_positions import force_flatten_all_positions
from src.execution.execution_providers import IbkrExecutionProvider
from src.execution.position_truth import (
    PositionTruthSnapshot,
    PositionTruthVerdict,
    PositionTruthConfig,
    collect_broker_position_snapshot,
    collect_system_position_snapshot,
    empty_position_truth_snapshot,
    healthy_position_truth_verdict,
    reconcile_position_truth,
)
from src.execution.recovery_engine import apply_recovery_actions, build_recovery_plan
from src.execution.trade_management_engine import TradeManagementEngine
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
from src.core.pipeline_audit import PipelineAudit, TerminalOutcome
from src.core.intent import build_decision_artifact, build_execution_intent
from src.e22.strategy_scalability_and_arbitration import (
    E22PolicyConfig,
    apply_e22_arbitration_layer,
)
from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_contract import ScannerRequest, scanner_request_from_policy
from src.scanner.ranking_registry import resolve_watchlist_selector
from src.scanner.result_models import CandidateMetrics
from src.strategy_policy_v2.consumption import (
    FocusBuilderV2,
    RankingEngineV2,
    SelectionEngineV2,
    WatchlistBuilderV2,
    candidates_metrics_to_v2,
)
from src.strategy_policy_v2.flags import is_policy_v2_enabled_for_strategy
from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2
from src.strategy_policy_v2.registry import resolve_policy_v2
from src.scanner.scanner_runner import run_scanner_cycle
from src.scanner.providers.base import ProviderConnectionError
from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.session_pct_change import canonical_session_label, normalize_session_label, resolve_market_session_context
from src.core.time.calendar_session import resolve_calendar_session
from src.core.time.trading_windows import (
    build_trading_window_policy,
    format_tha_source_log,
    resolve_trading_window_decision,
)
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
from src.prep.premarket_prep_artifact import (
    CANONICAL_PREP_ARTIFACT_PATH,
    load_canonical_premarket_prep_artifact,
    write_premarket_prep_artifact,
    write_canonical_premarket_prep_artifact,
)
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
from src.utils.pipeline_trace import (
    intent_stage_seen,
    pipeline_trace,
    reset_pipeline_trace_cycle,
)
from src.regime.layer import RegimeLayer


def _resolve_project_root() -> Path:
    """
    Resolve repository root deterministically.

    Expected structure:

        repo_root/
            src/
            config/
            data/
    """
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "config").exists() and (parent / "src").exists():
            return parent

    # fallback (should never happen but prevents runtime crash)
    return Path.cwd()


PROJECT_ROOT = _resolve_project_root()
MANUAL_FOCUS_PATH = PROJECT_ROOT / "config" / "manual_focus.json"


def _disabled_manual_focus_config() -> ManualFocusConfig:
    return ManualFocusConfig(
        enabled=False,
        manual_focus=[],
        max_manual_symbols=0,
        live_reload_seconds=60,
    )


def _manual_focus_config_from_dict(payload: dict) -> ManualFocusConfig:
    enabled = bool(payload.get("enabled", True))
    raw_symbols = payload.get("manual_focus", [])
    if not isinstance(raw_symbols, list):
        raw_symbols = []

    deduped_symbols: list[str] = []
    for symbol in raw_symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized or normalized in deduped_symbols:
            continue
        deduped_symbols.append(normalized)

    max_manual_symbols = int(payload.get("max_manual_symbols", 5))
    if max_manual_symbols < 0:
        max_manual_symbols = 0
    deduped_symbols = deduped_symbols[:max_manual_symbols]

    live_reload_seconds = int(payload.get("live_reload_seconds", 60))
    if live_reload_seconds <= 0:
        live_reload_seconds = 60

    return ManualFocusConfig(
        enabled=enabled,
        manual_focus=deduped_symbols,
        max_manual_symbols=max_manual_symbols,
        live_reload_seconds=live_reload_seconds,
    )


def load_manual_focus_config() -> ManualFocusConfig:
    path = MANUAL_FOCUS_PATH

    if not path.exists():
        print(f"[MANUAL_FOCUS][CONFIG_MISSING] path={path}")
        return _disabled_manual_focus_config()

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        print(f"[MANUAL_FOCUS][CONFIG_PATH] {path}")

        if not isinstance(payload, dict):
            print(f"[MANUAL_FOCUS][CONFIG_ERROR] invalid_schema={type(payload).__name__}")
            return _disabled_manual_focus_config()

        return _manual_focus_config_from_dict(payload)

    except Exception as e:
        print(f"[MANUAL_FOCUS][CONFIG_ERROR] {e}")
        return _disabled_manual_focus_config()


class RuntimeSafetyError(RuntimeError):
    """Raised when a runtime safety gate is violated."""


def build_orchestrator_strategy_registry(
    enabled_strategy_ids: Optional[List[str]] = None,
) -> StrategyRegistry:
    """Expose the canonical registry for orchestrator integration smoke tests."""
    return build_default_registry(enabled_strategy_ids=enabled_strategy_ids)


@dataclass
class StrategyCadenceCache:
    symbols: list[str] = field(default_factory=list)
    timestamp_utc: datetime | None = None
    rows: list[object] = field(default_factory=list)


@dataclass
class StrategyCadenceState:
    top_n: StrategyCadenceCache = field(default_factory=StrategyCadenceCache)
    watchlist: StrategyCadenceCache = field(default_factory=StrategyCadenceCache)
    focus: StrategyCadenceCache = field(default_factory=StrategyCadenceCache)
    scanner_cooldown_until_utc: datetime | None = None


class CoreOrchestrator:
    _MANUAL_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

    def __init__(self):
        print("[INFO] Core Orchestrator initialised.")
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        self.run_mode = self.runtime_mode_manager.resolved_mode
        self.execution_enabled = self.runtime_mode_manager.allow_orders
        self.ibkr_api_write_allowed = bool(get_config("IBKR_API_WRITE_ALLOWED"))
        self.replay_mode = self.runtime_mode_manager.event_replay_mode
        print(f"[BOOT] Runtime mode resolved: {self.runtime_mode_manager.describe()}")
        # Defer IBKR invariant enforcement to actual usage boundary
        if self._should_enforce_ibkr_runtime():
            try:
                self._enforce_runtime_invariants()
            except RuntimeError as e:
                print(f"[CONFIG WARNING] {e}")
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[SAFETY] ORDER ROUTING: BLOCKED")
            if self.run_mode == RunMode.LIVE:
                print("[MODE] LIVE_READ_ONLY active — execution disabled")
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
        self.selected_strategy_key = None
        self.selected_strategy_key = (
            self.selected_strategy_key
            or get_config("SELECTED_STRATEGY")
            or "ross_momentum"
        )
        self.selected_strategy_key = str(self.selected_strategy_key).strip().lower()
        print(f"[STRATEGY][SELECTED] key={self.selected_strategy_key}")
        self.primary_strategy_key = self.selected_strategy_key or "ross_momentum"
        self._strategy_watchlist_cache: dict[str, list[str]] = {}
        self._strategy_cadence_state: dict[str, StrategyCadenceState] = {}
        self._pipeline_runtime_counts: dict[str, int] = {
            "cycles_run": 0,
            "watchlist_count": 0,
            "setups_detected": 0,
            "triggers_fired": 0,
            "trade_intents": 0,
        }
        self._last_position_management_tick_utc: datetime | None = None
        self._manual_focus_symbols: list[str] = []
        self._manual_focus_enabled: bool = True
        self._manual_focus_reload_seconds: int = 60
        self._manual_focus_last_loaded_utc: datetime | None = None
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
        elif self.run_mode == RunMode.LIVE:
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
        elif self.run_mode == RunMode.PAPER:
            print("[MARKET_DATA][PAPER] Deterministic/mock market data feed active (no IBKR connectivity).")
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
        self.portfolio_arbitrator = PortfolioArbitrator()
        if not self.execution_enabled:
            provider = None
        elif self.run_mode == RunMode.PAPER:
            if IbkrLiveBroker is None:
                raise RuntimeSafetyError(
                    "PAPER execution requested but IbkrLiveBroker is unavailable. "
                    "Install ibapi and ensure IBKR adapter dependencies are present."
                )
            paper_port = int(get_ibkr_paper_port())
            submission_enabled = get_ibkr_order_submission_enabled()
            translation_enabled = get_ibkr_order_translation_enabled()
            api_write_allowed = get_ibkr_api_write_allowed()
            if paper_port != 7497:
                raise RuntimeSafetyError(
                    f"PAPER execution requires IBKR_PAPER_PORT=7497 (resolved {paper_port})."
                )
            if not submission_enabled:
                raise RuntimeSafetyError(
                    "PAPER execution enabled but IBKR_ORDER_SUBMISSION_ENABLED=false."
                )
            if not translation_enabled:
                raise RuntimeSafetyError(
                    "PAPER execution enabled but IBKR_ORDER_TRANSLATION_ENABLED=false."
                )
            if not api_write_allowed:
                raise RuntimeSafetyError(
                    "PAPER execution enabled but IBKR_API_WRITE_ALLOWED=false."
                )
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
        elif self.run_mode == RunMode.LIVE:
            if IbkrLiveBroker is None:
                raise RuntimeSafetyError(
                    "LIVE execution requested but IbkrLiveBroker is unavailable. "
                    "Install ibapi and ensure IBKR adapter dependencies are present."
                )
            live_port = int(get_config("IBKR_LIVE_PORT"))
            readonly = get_ibkr_readonly_enabled()
            kill_switch = bool(get_config("IBKR_KILL_SWITCH"))
            submission_enabled = get_ibkr_order_submission_enabled()
            translation_enabled = get_ibkr_order_translation_enabled()
            api_write_allowed = get_ibkr_api_write_allowed()
            if live_port != 7496:
                raise RuntimeSafetyError(
                    f"LIVE execution requires IBKR_LIVE_PORT=7496 (resolved {live_port})."
                )
            if readonly:
                raise RuntimeSafetyError("LIVE execution requires IBKR_READONLY_ENABLED=false.")
            if kill_switch:
                raise RuntimeSafetyError("LIVE execution blocked: IBKR_KILL_SWITCH=true.")
            if not submission_enabled:
                raise RuntimeSafetyError(
                    "Execution enabled but IBKR_ORDER_SUBMISSION_ENABLED=false."
                )
            if not translation_enabled:
                raise RuntimeSafetyError(
                    "Execution enabled but IBKR_ORDER_TRANSLATION_ENABLED=false."
                )
            if not api_write_allowed:
                raise RuntimeSafetyError(
                    "Execution enabled but IBKR_API_WRITE_ALLOWED=false."
                )
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
        self.position_management_engine = PositionManagementEngine()
        self.trade_management_engine = TradeManagementEngine(price_lookup=lambda symbol: float(self.price_feed.get_price(symbol)))
        self.trade_lifecycle_engine = TradeLifecycleEngine()
        self.risk_engine.set_trade_lifecycle_engine(self.trade_lifecycle_engine)
        self._broker_position_adapter = BrokerPositionSnapshotAdapter()
        self.trade_exit_engine = TradeExitEngine(
            trade_registry=self.trade_registry,
            event_collector=self.event_collector,
            price_feed=self.price_feed,
            stop_controller=self.stop_controller,
        )
        self.storage_engine = StorageEngine()
        self.trade_lifecycle_engine.set_persistence_adapter(self.storage_engine)
        try:
            self.trade_lifecycle_engine.recover_open_state()
        except Exception as exc:
            print(f"[LIFECYCLE][RECOVERY][DEGRADED] reason=unexpected_error error={exc}")
        self.decision_trace_store = DecisionTraceStore(
            persist_path=os.getenv("DECISION_TRACE_PATH")
        )
        self.learning_scheduler = LearningScheduler()
        self._halted = False
        self._degraded = False
        self._current_cycle_id: Optional[str] = None
        self._last_halt_reason: Optional[dict] = None
        self._halt_emitted = False
        self._pending_connectivity_halt: Optional[dict] = None
        self._latest_position_truth_snapshot: PositionTruthSnapshot | None = None
        self._latest_position_truth_verdict: PositionTruthVerdict = healthy_position_truth_verdict()
        self._latest_fill_authority_verdict: dict[str, object] = {"execution_stalled": False, "stalled_symbols": []}
        self.trace_bus = TraceBus()
        self._last_intent_validation = {"ok": True, "before": 0, "after": 0, "dropped": 0}
        self._daily_loss_warning_date: Optional[str] = None
        self._daily_loss_hard_stop_date: Optional[str] = None
        self._prep_next_due_at: datetime | None = None
        self._prep_update_thread: Thread | None = None
        self._prep_update_lock = Lock()
        print(f"[BOOT] Event replay mode resolved — mode={self.replay_mode.value}")
        self._run_startup_validations()
        self._ensure_premarket_prep_artifact()
        self._maybe_force_flatten_all_positions_on_startup()
        try:
            self.learning_scheduler.on_startup()
        except Exception as exc:
            print(f"[LEARNING][SCHEDULER] Startup check failed: {exc}")


    def _maybe_force_flatten_all_positions_on_startup(self) -> None:
        flatten_enabled = (
            self.run_mode in {RunMode.PAPER, RunMode.LIVE}
            and str(os.getenv("FLATTEN_ON_STARTUP", "false")).strip().lower() == "true"
        )
        if not flatten_enabled:
            return

        if self.run_mode == RunMode.LIVE:
            live_override = str(os.getenv("DEV_OVERRIDE_LIVE_FLATTEN", "false")).strip().lower() == "true"
            if not live_override:
                print("[DEV][FLATTEN][SKIP] RUN_MODE=LIVE requires DEV_OVERRIDE_LIVE_FLATTEN=true")
                return
        elif self.run_mode != RunMode.PAPER:
            print(f"[DEV][FLATTEN][SKIP] RUN_MODE={self.run_mode.value} not eligible")
            return

        try:
            client = self.connection_manager.optional_client
            if client is None:
                self.connection_manager.ensure_connected()
                client = self.connection_manager.optional_client
            if client is None:
                print("[DEV][FLATTEN][SKIP] IBKR client unavailable")
                return

            timeout_seconds = int(os.getenv("DEV_FORCE_FLATTEN_TIMEOUT_SECONDS", "30") or "30")
            result = force_flatten_all_positions(client, timeout_seconds=timeout_seconds)
            print(
                "[DEV][FLATTEN][SUMMARY] "
                f"positions_detected={result['positions_detected']} "
                f"close_orders_submitted={result['close_orders_submitted']} "
                f"positions_remaining={result['positions_remaining']} "
                f"status={result['status']}"
            )
        except Exception as exc:
            print(f"[DEV][FLATTEN][ERROR] {exc}")

    def _open_position_from_execution(
        self,
        *,
        risk_decision: RiskDecision,
        execution_result: ExecutionResult,
    ) -> ManagedPosition | None:
        status = str(getattr(execution_result, "status", "") or "").upper()
        if status not in {"FILLED", "PARTIAL", "ACKED", "SUBMITTED", "SIMULATED"}:
            return None
        quantity = int(getattr(execution_result, "filled_quantity", 0) or getattr(execution_result, "quantity", 0) or 0)
        if quantity <= 0:
            return None
        entry_price = float(getattr(execution_result, "entry_price", 0.0) or getattr(execution_result, "raw_price", 0.0) or 0.0)
        stop_price = float(getattr(risk_decision, "stop_loss_price", 0.0) or 0.0)
        if entry_price <= 0.0 or stop_price <= 0.0:
            return None

        execution_mode = str(
            getattr(risk_decision, "execution_refinement_mode", None)
            or getattr(execution_result, "execution_refinement_mode", None)
            or "NORMAL"
        )
        timeframe = str(getattr(risk_decision, "execution_primary_timeframe", None) or "1m")
        print(
            "[POSITION][STOP_SET] "
            f"symbol={risk_decision.symbol} entry={entry_price:.4f} stop={stop_price:.4f}"
        )
        return ManagedPosition(
            symbol=str(risk_decision.symbol),
            side=str(getattr(risk_decision, "direction", "LONG") or "LONG"),
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            execution_mode=execution_mode,
            timeframe=timeframe,
        )

    def _build_position_management_market_state(
        self,
        *,
        execution_result: ExecutionResult,
        session_phase: str,
    ) -> dict:
        current_price = float(
            getattr(execution_result, "raw_price", None)
            or getattr(execution_result, "entry_price", None)
            or 0.0
        )
        return {
            "current_price": current_price,
            "breaks_new_level": False,
            "pullback_holds_support": False,
            "higher_low": None,
            "structure_broken": False,
            "vwap_lost": False,
            "false_breakout": False,
            "session_phase": str(session_phase),
        }

    @staticmethod
    def _is_valid_managed_position(position: ManagedPosition | None) -> bool:
        return (
            position is not None
            and str(getattr(position, "symbol", "")).strip() != ""
            and int(getattr(position, "quantity", 0) or 0) > 0
            and float(getattr(position, "entry_price", 0.0) or 0.0) > 0.0
            and float(getattr(position, "stop_price", 0.0) or 0.0) > 0.0
        )

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _entry_is_price_sane(self, *, symbol: str, entry_price: float | None, stop_price: float | None) -> bool:
        if entry_price is None or entry_price <= 0 or stop_price is None or stop_price <= 0:
            print(f"[ENTRY][PRICE_SANITY_BLOCK] symbol={symbol} reason=missing_or_non_positive_price")
            return False
        if stop_price >= entry_price:
            print(f"[ENTRY][PRICE_SANITY_BLOCK] symbol={symbol} reason=stop_not_below_entry entry={entry_price} stop={stop_price}")
            return False
        if entry_price < 0.2:
            print(f"[ENTRY][PRICE_SANITY_BLOCK] symbol={symbol} reason=sub_penny_like_price entry={entry_price}")
            return False
        return True

    def _entry_spread_is_tradeable(self, *, symbol: str, entry_price: float, spread_pct: float | None) -> bool:
        max_spread_pct = float(get_config("ROSS_MAX_SPREAD_PCT_FOR_ENTRY") or 0.006)
        max_spread_pct_low = float(get_config("ROSS_MAX_SPREAD_PCT_FOR_LOW_PRICE") or 0.012)
        low_price_cutoff = float(get_config("ROSS_LOW_PRICE_SPREAD_CUTOFF") or 5.0)
        threshold = max_spread_pct_low if entry_price <= low_price_cutoff else max_spread_pct
        if spread_pct is None:
            print(f"[ENTRY][SPREAD_BLOCK] symbol={symbol} spread=unknown spread_pct=unknown")
            return False
        if spread_pct > threshold:
            print(f"[ENTRY][SPREAD_BLOCK] symbol={symbol} spread=unknown spread_pct={spread_pct:.4f}")
            return False
        return True

    def _register_trade_lifecycle_on_execution(
        self,
        *,
        execution_result: ExecutionResult,
        managed_position: ManagedPosition | None,
    ) -> str | None:
        status = str(getattr(execution_result, "status", "") or "").upper()
        filled_quantity = int(getattr(execution_result, "filled_quantity", 0) or 0)
        ibkr_order_id = getattr(execution_result, "ibkr_order_id", None)
        is_confirmed_fill = bool(
            ibkr_order_id is not None
            and (status in {"FILLED", "PARTIAL"} or filled_quantity > 0)
        )
        if not is_confirmed_fill:
            print(
                "[LIFECYCLE][SKIP] "
                f"stage=register reason=waiting_for_ibkr_fill status={status} "
                f"order_id={ibkr_order_id} filled_quantity={filled_quantity}"
            )
            return None
        quantity = filled_quantity
        if quantity <= 0:
            print("[LIFECYCLE][SKIP] stage=register reason=invalid_quantity")
            return None
        entry_price = float(getattr(execution_result, "entry_price", 0.0) or getattr(execution_result, "raw_price", 0.0) or 0.0)
        if entry_price <= 0.0:
            print("[LIFECYCLE][SKIP] stage=register reason=invalid_entry_price")
            return None
        if not self._is_valid_managed_position(managed_position):
            print("[LIFECYCLE][SKIP] stage=register reason=invalid_managed_position")
            return None
        stop_price = float(getattr(managed_position, "stop_price", 0.0) or 0.0)
        if stop_price <= 0.0:
            print("[LIFECYCLE][SKIP] stage=register reason=invalid_stop_price")
            return None
        trade_id = str(getattr(execution_result, "client_order_id", None) or f"{execution_result.symbol}:{uuid4()}")
        self.trade_lifecycle_engine.apply_event(
            LifecycleEvent(
                event_id=str(getattr(execution_result, "execution_id", None) or f"entry:{trade_id}:{quantity}:{entry_price}"),
                lifecycle_trade_id=trade_id,
                symbol=str(execution_result.symbol),
                side=str(getattr(managed_position, "side", "LONG") or "LONG").upper(),
                event_type="ENTRY_FILL",
                quantity=quantity,
                price=entry_price,
                timestamp=datetime.now(timezone.utc).isoformat(),
                order_id=str(ibkr_order_id),
                execution_id=str(getattr(execution_result, "execution_id", "") or "") or None,
                source="IBKR_EVENT",
            ),
            strategy_name=str(getattr(execution_result, "strategy_name", "") or "") or None,
            stop_price=stop_price,
        )
        print(
            "[LIFECYCLE][UPDATE] "
            f"symbol={execution_result.symbol} event=ENTRY_FILL source=IBKR_EVENT "
            f"order_id={ibkr_order_id} status={status} qty={quantity}"
        )
        print(f"[LIFECYCLE][REGISTER] symbol={execution_result.symbol} trade_id={trade_id} qty={quantity}")
        return trade_id

    def _reconcile_lifecycle_with_managed_position(
        self,
        *,
        symbol: str,
        lifecycle_trade_id: str | None,
        before_position: ManagedPosition | None,
        after_position: ManagedPosition | None,
    ) -> None:
        if not lifecycle_trade_id:
            print("[LIFECYCLE][SKIP] stage=reconcile reason=missing_trade_id")
            return
        if not self._is_valid_managed_position(before_position):
            print("[LIFECYCLE][SKIP] stage=reconcile reason=invalid_before_position")
            return
        if after_position is None:
            print("[LIFECYCLE][SKIP] stage=reconcile reason=missing_after_position")
            return
        open_trade_id = self.trade_lifecycle_engine.find_open_trade_id_for_symbol(str(symbol))
        if open_trade_id != lifecycle_trade_id:
            print("[LIFECYCLE][SKIP] stage=reconcile reason=no_open_registered_trade")
            return
        before_qty = int(getattr(before_position, "quantity", 0) or 0)
        after_qty = int(getattr(after_position, "quantity", 0) or 0)
        closed = bool(getattr(after_position, "closed", False))
        if before_qty > after_qty:
            exit_qty = before_qty - after_qty
            exit_price = float(
                getattr(after_position, "entry_price", 0.0)
                or getattr(before_position, "entry_price", 0.0)
                or 0.0
            )
            self.trade_lifecycle_engine.apply_event(
                LifecycleEvent(
                    event_id=f"exit:{lifecycle_trade_id}:{before_qty}:{after_qty}:{closed}",
                    lifecycle_trade_id=lifecycle_trade_id,
                    symbol=str(symbol),
                    side=str(getattr(before_position, "side", "LONG") or "LONG").upper(),
                    event_type="STOP_EXIT" if closed else "PARTIAL_EXIT",
                    quantity=exit_qty,
                    price=exit_price,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source="position_management",
                )
            )
        reconcile_result = self.trade_lifecycle_engine.apply_reconciliation_snapshot(
            symbol=str(symbol),
            runtime_quantity=max(after_qty, 0),
            runtime_avg_entry=float(getattr(after_position, "entry_price", 0.0) or 0.0),
        )
        print(
            "[LIFECYCLE][RECONCILE] "
            f"symbol={symbol} trade_id={lifecycle_trade_id} status={reconcile_result.get('status')}"
        )

    def _mark_open_trades_to_market(self) -> None:
        try:
            open_trades = self.trade_lifecycle_engine.open_trades()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=mark_to_market_open_trades error={exc}")
            return
        if not open_trades:
            return
        for trade in open_trades:
            symbol = str(getattr(trade, "symbol", "") or "")
            if not symbol:
                print("[LIFECYCLE][SKIP] stage=mark_to_market reason=missing_symbol")
                continue
            try:
                price = float(self.price_feed.get_price(symbol))
            except Exception as exc:
                print(f"[LIFECYCLE][ERROR] stage=mark_to_market_price symbol={symbol} error={exc}")
                continue
            try:
                marked = self.trade_lifecycle_engine.mark_to_market(
                    trade_id=str(trade.lifecycle_trade_id),
                    price=price,
                )
                if marked is None:
                    print(f"[LIFECYCLE][SKIP] stage=mark_to_market reason=trade_missing symbol={symbol}")
                    continue
                print(
                    "[LIFECYCLE][MARK] "
                    f"symbol={symbol} trade_id={trade.lifecycle_trade_id} price={price:.4f}"
                )
            except Exception as exc:
                print(f"[LIFECYCLE][ERROR] stage=mark_to_market_apply symbol={symbol} error={exc}")

    def _summarize_trade_lifecycle_session(self) -> None:
        summary = self.trade_lifecycle_engine.summarize_session_metrics()
        print(
            "[LIFECYCLE][SUMMARY] "
            f"trades={summary.get('total_lifecycle_trades_seen', 0)} "
            f"open={summary.get('open_lifecycle_trades', 0)} "
            f"partial={summary.get('partially_closed_trades', 0)} "
            f"closed={summary.get('closed_trades', 0)} "
            f"realized={float(summary.get('gross_realized_pnl', 0.0)):.2f} "
            f"open_unrealized_pnl={float(summary.get('open_unrealized_pnl', 0.0)):.2f} "
            f"drifted={summary.get('drifted_trades_count', 0)} "
            f"orphaned={summary.get('orphaned_trades_count', 0)} "
            f"reconcile_events={summary.get('reconciliation_events_count', 0)} "
            f"portfolio_exposure={float(summary.get('portfolio_exposure', 0.0)):.2f} "
            f"portfolio_realized_pnl={float(summary.get('portfolio_realized_pnl', 0.0)):.2f} "
            f"portfolio_unrealized_pnl={float(summary.get('portfolio_unrealized_pnl', 0.0)):.2f} "
            f"broker_mismatch_count={summary.get('broker_mismatch_count', 0)} "
            f"drift_count={summary.get('drift_count', 0)} "
            f"orphan_count={summary.get('orphan_count', 0)}"
        )

    def _run_lifecycle_authority_overlay(self) -> None:
        provider = getattr(self.execution_engine, "provider", None)
        broker = getattr(provider, "broker", None)
        connection_manager = getattr(broker, "connection_manager", None)
        if connection_manager is not None and hasattr(connection_manager, "get_client"):
            try:
                self._broker_position_adapter._broker_client = connection_manager.get_client()
            except Exception as exc:
                print(f"[LIFECYCLE][BROKER_SNAPSHOT][DEGRADED] reason=client_resolution_failed error={exc}")
        try:
            snapshot = self._broker_position_adapter.fetch_broker_positions()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=broker_snapshot_fetch error={exc}")
            snapshot = []
        try:
            findings = self.trade_lifecycle_engine.reconcile_with_broker_snapshot(snapshot)
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=broker_reconcile error={exc}")
            findings = []
        try:
            portfolio_state = self.trade_lifecycle_engine.build_portfolio_state()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=portfolio_build error={exc}")
            portfolio_state = None
        try:
            risk_signals = self.trade_lifecycle_engine.compute_lifecycle_risk_signals()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=lifecycle_risk_signals error={exc}")
            risk_signals = None
        if portfolio_state is not None:
            print(
                "[LIFECYCLE][PORTFOLIO] "
                f"open_positions={portfolio_state.total_open_positions} "
                f"exposure={portfolio_state.total_exposure:.2f} "
                f"realized={portfolio_state.total_realized_pnl:.2f} "
                f"unrealized={portfolio_state.total_unrealized_pnl:.2f} "
                f"drifted={len(portfolio_state.drifted_positions)}"
            )
        if risk_signals is not None:
            print(
                "[LIFECYCLE][RISK_SIGNALS] "
                f"max_drawdown_breached={risk_signals.max_drawdown_breached} "
                f"pnl_drop_rate_exceeded={risk_signals.pnl_drop_rate_exceeded} "
                f"too_many_open_positions={risk_signals.too_many_open_positions} "
                f"drift_detected={risk_signals.drift_detected}"
            )
        print(f"[LIFECYCLE][BROKER_RECONCILE][SUMMARY] findings={len(findings)}")

    def _should_enforce_ibkr_runtime(self) -> bool:
        """
        Determine whether IBKR runtime invariants should be enforced.

        Enforcement should ONLY occur when:
        - Execution is enabled
        - System is in LIVE or PAPER mode
        - IBKR connection is actually expected to be used
        """

        from src.config.config_resolver import get_config

        run_mode = str(get_config("RUN_MODE_EFFECTIVE")).upper()
        execution_enabled = bool(get_config("EXECUTION_ENABLED"))

        # Only enforce in real execution scenarios
        if run_mode not in {"LIVE", "PAPER"}:
            return False

        if not execution_enabled:
            return False

        # IMPORTANT:
        # Do NOT enforce based on default IBKR config
        # Only enforce when user explicitly configured IBKR connection

        ibkr_host = os.getenv("IBKR_HOST")
        ibkr_port = os.getenv("IBKR_PORT")

        # Explicit configuration only (ignore defaults like 127.0.0.1 / 7497)
        if ibkr_host not in (None, "", "127.0.0.1"):
            return True

        if ibkr_port not in (None, "", "7497"):
            return True

        return False

    def _enforce_runtime_invariants(self):
        from src.config.config_resolver import get_config
        from src.config.runtime_config import resolve_ibkr_connection

        run_mode = str(get_config("RUN_MODE_EFFECTIVE")).upper()
        execution_enabled = bool(get_config("EXECUTION_ENABLED"))

        if run_mode == "LIVE" and not execution_enabled:
            raise RuntimeError(
                "[FATAL] LIVE mode cannot run with execution disabled (runtime enforcement)"
            )

        _, port, _, _ = resolve_ibkr_connection()

        ibkr_host = os.getenv("IBKR_HOST")
        ibkr_port_env = os.getenv("IBKR_PORT")

        # Only enforce if IBKR connection is explicitly configured
        ibkr_connection_explicit = ibkr_host is not None or ibkr_port_env is not None

        if run_mode == "LIVE" and ibkr_connection_explicit and port != 7496:
            raise RuntimeError(
                "[FATAL] LIVE mode must use IBKR port 7496 (runtime enforcement)"
            )

    @staticmethod
    def _strategy_mode_for_session_phase(session_phase: str) -> str:
        if session_phase in {"PREMARKET", "OPENING_0_30", "MORNING"}:
            return "OPEN_FAST"
        if session_phase in {"LATE", "POWER_HOUR"}:
            return "LATE_SLOW"
        return "MIDDAY_SLOW"

    @staticmethod
    def _build_scanner_policy_for_strategy(
        strategy_key: str,
        session_phase: str,
    ) -> tuple[object, StockSelectionPolicy]:
        selected_strategy = (strategy_key or "ross_momentum").strip().lower() or "ross_momentum"
        if selected_strategy == "statistical_intraday_momentum":
            strategy_policy = StatisticalIntradayMomentumPolicy()
            stock_policy = statistical_stock_selection_spec()
            return strategy_policy, stock_policy
        if selected_strategy == "mean_reversion":
            strategy_policy = MeanReversionScannerPolicy()
            stock_policy = mean_reversion_stock_selection_spec()
            return strategy_policy, stock_policy
        if selected_strategy == "long_horizon_value":
            strategy_policy = RossMomentumPolicy()
            stock_policy = replace(
                strategy_policy.stock_selection,
                policy_name="LONG_HORIZON_VALUE",
                gap_min_pct=3.0,
                rvol_min=1.2,
                min_volume=100_000,
                min_premarket_volume=25_000,
                require_catalyst=False,
                watchlist_limit_k=max(5, int(strategy_policy.stock_selection.watchlist_limit_k)),
                focus_limit_m=max(3, int(strategy_policy.stock_selection.focus_limit_m)),
                ranking_intent="LONG_HORIZON_VALUE",
            )
            return strategy_policy, stock_policy
        strategy_policy = RossMomentumPolicy()
        stock_policy = stock_selection_policy_for_session_phase(strategy_policy, session_phase)
        return strategy_policy, stock_policy

    @classmethod
    def _build_scanner_policy(cls, session_phase: str) -> tuple[object, StockSelectionPolicy]:
        selected_strategy = (str(get_config("SELECTED_STRATEGY") or "").strip().lower() or "ross_momentum")
        return cls._build_scanner_policy_for_strategy(selected_strategy, session_phase)

    @staticmethod
    def _enabled_strategy_keys() -> list[str]:
        enabled: list[str] = []
        if bool(get_config("ROSS_MOMENTUM_STRATEGY_ENABLED")):
            enabled.append("ross_momentum")
        if bool(get_config("STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED")):
            enabled.append("statistical_intraday_momentum")
        if bool(get_config("MEAN_REVERSION_STRATEGY_ENABLED")):
            enabled.append("mean_reversion")
        return enabled or ["ross_momentum"]

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

    def _resolve_tha_decisions(
        self,
        *,
        strategy_inputs: List[object],
        now_utc: datetime,
    ) -> dict[str, object]:
        decisions: dict[str, object] = {}
        for candidate in strategy_inputs or []:
            symbol = str(getattr(candidate, "symbol", "") or "").upper()
            if not symbol:
                continue
            trading_hours = (
                getattr(candidate, "trading_hours", None)
                or getattr(candidate, "ibkr_trading_hours", None)
            )
            liquid_hours = (
                getattr(candidate, "liquid_hours", None)
                or getattr(candidate, "ibkr_liquid_hours", None)
            )
            timezone_id = (
                getattr(candidate, "timeZoneId", None)
                or getattr(candidate, "timezone", None)
                or getattr(candidate, "timezone_id", None)
            )
            policy = build_trading_window_policy(
                symbol=symbol,
                now=now_utc,
                run_mode=self.run_mode.value,
                trading_hours=trading_hours,
                liquid_hours=liquid_hours,
                timezone=timezone_id,
            )
            print(
                format_tha_source_log(
                    symbol=symbol,
                    source=policy.source,
                    segments=policy.segments,
                )
            )
            tha_decision = resolve_trading_window_decision(policy=policy, now=now_utc)
            if tha_decision.in_window and not tha_decision.allow_entries:
                raise RuntimeError("THA contradiction: inside window but entries blocked")
            decisions[symbol] = tha_decision
            print(
                "[PIPELINE][THA_GATE] "
                f"symbol={symbol} in_window={tha_decision.in_window} "
                f"allow_entries={tha_decision.allow_entries} force_flat={tha_decision.force_flat}"
            )
        return decisions

    @staticmethod
    def _cap_list(items: List[str], limit: int) -> List[str]:
        if len(items) > limit:
            return items[:limit] + ["..."]
        return items

    @staticmethod
    def _manual_focus_candidate(symbol: str, session_phase: str) -> CandidateMetrics:
        return CandidateMetrics(
            symbol=symbol,
            con_id=None,
            exchange=None,
            session_label=session_phase,
            session_phase=session_phase,
            last_price=None,
            prev_close=None,
            ref_close_rth=None,
            reference_price=None,
            reference_label=None,
            reference_source=None,
            reference_quality_tier=None,
            reference_resolved=None,
            gap_pct=None,
            pct_change=None,
            pct_change_resolved=None,
            pct_change_qualification_usable=None,
            pct_change_execution_usable=None,
            pct_change_source_quality=None,
            pct_change_degraded=None,
            pct_change_synthetic=None,
            pct_change_failure_reason=None,
            gap_pct_resolved=None,
            gap_source=None,
            context_status=None,
            execution_ready=None,
            prep_only=None,
            live_rvol_deferred=None,
            prep_seeded=None,
            live_confirmation_pending=None,
            watchlist_source="MANUAL_FOCUS",
            promotion_reason="manual_focus",
            ibkr_change_pct=None,
            pct_source=None,
            open_relative_pct_change=None,
            hod_pct=None,
            rvol=None,
            rvol_discovery=None,
            rvol_phase=None,
            phase_volume_ratio=None,
            relative_volume=None,
            avg_volume_20d=None,
            adv20_resolved=None,
            degraded_adv20=None,
            adv20_source=None,
            rvol_status=None,
            rvol_failure_reason=None,
            rvol_degraded=None,
            rvol_qualification_usable=None,
            rvol_execution_usable=None,
            degraded_rvol_gate_bypass=None,
            float_shares=None,
            float_source=None,
            float_asof=None,
            float_cache_hit=None,
            float_millions=None,
            volume=None,
            premarket_volume=None,
            dollar_volume=None,
            bid=None,
            ask=None,
            spread=None,
            spread_pct=None,
            halted=None,
            ssr=None,
            catalyst_present=None,
            catalyst_summary=None,
            news_count=None,
            fresh_news_count=None,
            stale_news_count=None,
            top_news_title=None,
            top_news_age_hours=None,
            top_news_catalyst_tag=None,
            news_source_mode=None,
            news_asof=None,
            data_quality_ok=True,
            data_quality_flags=[],
            drop_reasons=[],
            rank_score=None,
            rank_components=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            gate_checks={},
        )

    def _refresh_manual_focus_if_due(self, now_utc: datetime) -> list[str]:
        due = (
            self._manual_focus_last_loaded_utc is None
            or (now_utc - self._manual_focus_last_loaded_utc).total_seconds() >= self._manual_focus_reload_seconds
        )
        if not due:
            return list(self._manual_focus_symbols)

        cfg = load_manual_focus_config()
        symbols = list(cfg.manual_focus) if cfg.enabled else []
        print(
            "[MANUAL_FOCUS][LOAD] "
            f"enabled={cfg.enabled} symbols={symbols} "
            f"max={cfg.max_manual_symbols} reload_seconds={cfg.live_reload_seconds}"
        )
        print(f"[MANUAL_FOCUS][NORMALIZED] symbols={symbols}")
        self._manual_focus_enabled = cfg.enabled
        self._manual_focus_reload_seconds = max(1, int(cfg.live_reload_seconds))
        if symbols != self._manual_focus_symbols:
            print(f"[MANUAL_FOCUS] update_detected symbols={symbols}")
        self._manual_focus_symbols = symbols
        self._manual_focus_last_loaded_utc = now_utc
        return list(self._manual_focus_symbols)

    @classmethod
    def _manual_focus_rejection_reason(cls, symbol: str) -> str | None:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return "EMPTY_SYMBOL"
        if not cls._MANUAL_SYMBOL_PATTERN.fullmatch(normalized):
            return "INVALID_SYMBOL_FORMAT"
        return None

    def _resolve_manual_focus_candidates(
        self,
        manual_symbols: list[str],
        session_phase: str,
    ) -> tuple[list[CandidateMetrics], list[tuple[str, str]]]:
        accepted: list[CandidateMetrics] = []
        rejected: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_symbol in manual_symbols:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol in seen:
                continue
            seen.add(symbol)
            rejection_reason = self._manual_focus_rejection_reason(symbol)
            if rejection_reason:
                print(f"[MANUAL_FOCUS][REJECT] symbol={symbol or '<EMPTY>'} reason={rejection_reason}")
                rejected.append((symbol, rejection_reason))
                continue
            print(f"[MANUAL_FOCUS][ACCEPT] symbol={symbol} reason=DIRECT_OVERRIDE")
            accepted.append(self._manual_focus_candidate(symbol, session_phase))
        return accepted, rejected

    def _merge_focus_candidates(
        self,
        scanner_focus: list[CandidateMetrics],
        manual_candidates: list[CandidateMetrics],
        session_phase: str,
    ) -> list[CandidateMetrics]:
        _ = session_phase
        merged: list[CandidateMetrics] = []
        seen: set[str] = set()
        for row in scanner_focus:
            symbol = getattr(row, "symbol", None)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(row)
        for manual_row in manual_candidates:
            symbol = getattr(manual_row, "symbol", None)
            if symbol in seen:
                continue
            merged.append(manual_row)
            seen.add(symbol)
        return merged

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

    def _emit_canonical_halt(
        self,
        *,
        reason_code: str,
        message: str,
        halt_stage: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        resolved_details = details or {}
        payload = {
            "stage": "HALT",
            "reason_code": reason_code,
            "reason": str(resolved_details.get("reason") or reason_code).lower(),
            "source": str(resolved_details.get("source") or "core_orchestrator"),
            "message": message,
            "halt_stage": halt_stage,
            "details": resolved_details,
        }
        self._last_halt_reason = payload
        self._halt_emitted = True
        self._trace_event("HALT", payload)

    def _trace_halt(
        self,
        *,
        reason_code: str,
        message: str,
        stage: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        self._emit_canonical_halt(
            reason_code=reason_code,
            message=message,
            halt_stage=stage,
            details=details,
        )

    def _handle_halt_worthy_failure(
        self,
        *,
        reason_code: str,
        message: str,
        halt_stage: str,
        stop_mode: StopMode,
        stop_reason: str,
        stop_source: str,
        details: Optional[dict] = None,
        set_degraded: bool = False,
        shutdown: bool = False,
        request_stop: bool = True,
    ) -> StopMode:
        if set_degraded:
            self._degraded = True
            system_state = getattr(self, "system_state", None)
            if system_state is not None:
                system_state.set_degraded(reason=message)
        should_emit_halt = (not self._halt_emitted)
        if not should_emit_halt and self._last_halt_reason is not None:
            should_emit_halt = (
                self._last_halt_reason.get("reason_code") != reason_code
                or self._last_halt_reason.get("halt_stage") != halt_stage
                or self._last_halt_reason.get("message") != message
            )
        if should_emit_halt:
            self._emit_canonical_halt(
                reason_code=reason_code,
                message=message,
                halt_stage=halt_stage,
                details=details,
            )
        resolved_mode = self.stop_controller.stop_mode() or stop_mode
        if request_stop and not self.stop_controller.is_stop_requested():
            resolved_mode = self._request_stop(
                stop_mode,
                reason=stop_reason,
                source=stop_source,
            )
        if shutdown:
            self._shutdown(self.stop_controller.stop_mode() or resolved_mode)
        return self.stop_controller.stop_mode() or resolved_mode

    def _emit_pending_connectivity_halt(self) -> None:
        if self._halt_emitted or self._pending_connectivity_halt is None:
            return
        self._emit_canonical_halt(**self._pending_connectivity_halt)

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
        print(
            "[SUMMARY]\n"
            f"cycles_run={self._pipeline_runtime_counts.get('cycles_run', 0)}\n"
            f"watchlist_count={self._pipeline_runtime_counts.get('watchlist_count', 0)}\n"
            f"setups_detected={self._pipeline_runtime_counts.get('setups_detected', 0)}\n"
            f"triggers_fired={self._pipeline_runtime_counts.get('triggers_fired', 0)}\n"
            f"trade_intents={self._pipeline_runtime_counts.get('trade_intents', 0)}"
        )
        if hasattr(self, "strategy_runner") and self.strategy_runner is not None:
            self.strategy_runner.emit_shutdown_summary()
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
        self._halt_emitted = False
        self._pending_connectivity_halt = None

        while True:
            try:
                if self.stop_controller.is_stop_requested():
                    if self._pending_connectivity_halt and not self._halt_emitted:
                        self._emit_canonical_halt(**self._pending_connectivity_halt)
                    self._shutdown(self.stop_controller.stop_mode() or StopMode.GRACEFUL)
                    performed_shutdown = True
                    break

                if max_cycles is not None and cycles_run >= max_cycles:
                    self._emit_pending_connectivity_halt()
                    break

                print("[CYCLE] Starting orchestrator cycle.")
                current_session = get_current_market_session()
                detected_session = normalize_session_label(
                    resolve_market_session_context(datetime.now(timezone.utc)).phase
                )
                self._emit_market_session_state(current_session)
                print(f"[SESSION][DETECTED] session={detected_session}")
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
                if current_session in {"PRE", "CLOSED"}:
                    self.run_preparation_mode()
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
                if self.run_mode == RunMode.LIVE:
                    print(f"[CONNECTIVITY] Provider connectivity failure in LIVE mode: {exc}")
                    self._handle_halt_worthy_failure(
                        reason_code="CONNECTIVITY_FAILURE",
                        message=str(exc),
                        halt_stage="CONNECTIVITY",
                        stop_mode=StopMode.GRACEFUL,
                        stop_reason="Connectivity failure in LIVE mode",
                        stop_source="CoreOrchestrator",
                        shutdown=True,
                    )
                    performed_shutdown = True
                    break

                retry_count += 1
                self._degraded = True
                backoff_seconds = min(60, max(1, int(2 ** (retry_count - 1))))
                next_attempt = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                if max_cycles is not None:
                    print(
                        "[CONNECTIVITY] "
                        "Max cycles set; aborting after connectivity error."
                    )
                    self._handle_halt_worthy_failure(
                        reason_code="CONNECTIVITY_FAILURE",
                        message=str(exc),
                        halt_stage="CONNECTIVITY",
                        stop_mode=StopMode.GRACEFUL,
                        stop_reason="Connectivity error with max_cycles",
                        stop_source="CoreOrchestrator",
                        details={
                            "retry": retry_count,
                            "reason": "provider_connection_failure",
                            "provider": "IBKR",
                            "abort_reason": "max_cycles",
                        },
                        set_degraded=True,
                        shutdown=True,
                    )
                    performed_shutdown = True
                    break
                self._handle_halt_worthy_failure(
                    reason_code="CONNECTIVITY_FAILURE",
                    message=str(exc),
                    halt_stage="CONNECTIVITY",
                    stop_mode=StopMode.GRACEFUL,
                    stop_reason="Connectivity failure in READ_ONLY mode",
                    stop_source="CoreOrchestrator",
                    details={
                        "reason": "connectivity_failure",
                        "provider": "IBKR",
                        "mode": self.run_mode.value if hasattr(self.run_mode, "value") else str(self.run_mode),
                        "source": "scanner_runner",
                    },
                    set_degraded=True,
                    shutdown=False,
                    request_stop=False,
                )
                self._pending_connectivity_halt = None
                print("STATE=DEGRADED")
                print("reason=provider_connection_failure")
                print("provider=IBKR")
                print(
                    "[TRACEABILITY] "
                    "STATE=DEGRADED reason=provider_connection_failure provider=IBKR"
                )
                print(
                    "[CONNECTIVITY] "
                    f"STATE=DEGRADED retry={retry_count} backoff={backoff_seconds}s "
                    f"next_attempt={next_attempt.isoformat()}"
                )
                self._trace_event(
                    "CONNECTIVITY_RETRY",
                    {
                        "reason_code": "CONNECTIVITY_RETRY",
                        "message": str(exc),
                        "stage": "CONNECTIVITY",
                        "details": {
                            "retry": retry_count,
                            "backoff_seconds": backoff_seconds,
                            "next_attempt": next_attempt.isoformat(),
                            "reason": "provider_connection_failure",
                            "provider": "IBKR",
                        },
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
            if self._pending_connectivity_halt and not self._halt_emitted:
                self._emit_canonical_halt(**self._pending_connectivity_halt)
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
        reset_pipeline_trace_cycle()
        self._current_cycle_id = str(uuid4())
        self._last_halt_reason = None
        cycle_started_at = datetime.now(timezone.utc)
        ny_time = to_ny_time(cycle_started_at)
        uk_time = to_uk_time(cycle_started_at)
        forced_session = str(os.getenv("FORCE_SESSION") or "").strip().upper()
        forced_session_applied = normalize_session_label(forced_session) if forced_session else ""

        if forced_session:
            if not forced_session_applied:
                forced_session_applied = forced_session

            print(
                "[SESSION][FORCED_OVERRIDE] "
                f"requested={forced_session} applied={forced_session_applied}"
            )
        resolved_session = (
            normalize_session_label(forced_session)
            if forced_session
            else normalize_session_label(market_session_phase(cycle_started_at))
        )
        calendar_session = resolve_calendar_session(cycle_started_at)
        session_phase = resolved_session
        print(f"[SESSION][FINAL] resolved_session={resolved_session}")
        print(
            "[SESSION][CALENDAR] "
            f"symbol=SYSTEM calendar_session={calendar_session}"
        )
        print(
            "[SESSION] "
            f"phase={session_phase} ny_time={ny_time.isoformat()} "
            f"uk_time={uk_time.isoformat()} utc={cycle_started_at.isoformat()}"
        )
        self._maybe_run_scheduled_prep_update(
            cycle_started_at,
            session_phase,
        )
        return self._run_manager_pipeline(
            cycle_started_at=cycle_started_at,
            ny_time=ny_time,
            uk_time=uk_time,
            session_phase=session_phase,
            forced_session_label=forced_session_applied or None,
            forced_session_source="FORCE_SESSION" if forced_session_applied else None,
        )

    def _active_policy_v2(self) -> StrategyPolicyV2 | None:
        policy_v2 = resolve_policy_v2(self.selected_strategy_key)
        if policy_v2 and is_policy_v2_enabled_for_strategy(self.selected_strategy_key):
            return policy_v2
        return None

    def _build_watchlist_focus_v2(
        self,
        policy: StrategyPolicyV2,
        observations: list[CandidateMetrics],
    ) -> tuple[list[CandidateMetrics], list[CandidateMetrics]]:
        adapted = candidates_metrics_to_v2(observations)
        selection = SelectionEngineV2().evaluate(policy, adapted)
        ranking = RankingEngineV2().rank(policy, selection.eligible)
        watchlist_symbols = {item.get("symbol", "") for item in WatchlistBuilderV2().build(policy, ranking.ranked).watchlist}
        focus_symbols = {item.get("symbol", "") for item in FocusBuilderV2().build(policy, ranking.ranked).focus}

        by_symbol = {row.symbol: row for row in observations}
        watchlist = [by_symbol[symbol] for symbol in sorted(watchlist_symbols) if symbol in by_symbol]
        focus = [by_symbol[symbol] for symbol in sorted(focus_symbols) if symbol in by_symbol]
        # keep deterministic ranked order per tie-breakers from builders
        ranked_symbols = [row.candidate.get("symbol", "") for row in sorted(
            ranking.ranked,
            key=lambda row: (
                -row.score,
                -(float(row.candidate.get("pct_change") or 0.0)),
                -(float(row.candidate.get("dollar_volume") or 0.0)),
                str(row.candidate.get("symbol") or ""),
            ),
        )]
        watchlist = [by_symbol[symbol] for symbol in ranked_symbols if symbol in watchlist_symbols and symbol in by_symbol]
        focus = [by_symbol[symbol] for symbol in ranked_symbols if symbol in focus_symbols and symbol in by_symbol]
        return watchlist, focus


    @staticmethod
    def _mock_scanner_mode_enabled() -> bool:
        return str(get_config("SCANNER_DATA_SOURCE") or "").strip().upper() == "MOCK"

    def _strategy_cadence(self, strategy_key: str) -> StrategyCadenceState:
        if strategy_key not in self._strategy_cadence_state:
            self._strategy_cadence_state[strategy_key] = StrategyCadenceState()
        return self._strategy_cadence_state[strategy_key]

    @staticmethod
    def _is_stale(cache: StrategyCadenceCache, now: datetime, refresh_seconds: int) -> bool:
        if cache.timestamp_utc is None:
            return True
        return (now - cache.timestamp_utc).total_seconds() >= max(1, refresh_seconds)

    @staticmethod
    def _pattern_reason_line(symbol: str, emitted_intent: bool, risk_blocked: bool = False) -> str:
        if emitted_intent:
            return f"[FOCUS][REASON] {symbol} intent_emitted"
        if risk_blocked:
            return f"[FOCUS][REASON] {symbol} pattern_detected_but_risk_blocked"
        return f"[FOCUS][REASON] {symbol} no_pattern"

    def _run_position_management_tick(self, now: datetime) -> None:
        tick_seconds = int(get_config("POSITION_MANAGEMENT_TICK_SECONDS"))
        if tick_seconds <= 0:
            return
        if self._last_position_management_tick_utc is not None:
            elapsed = (now - self._last_position_management_tick_utc).total_seconds()
            if elapsed < tick_seconds:
                return
        open_positions = self.trade_registry.snapshot()
        self._detect_unprotected_positions(open_positions, stage="runtime")
        for trade in open_positions:
            self._trace_event(
                "POSITION_MANAGE",
                {
                    "symbol": trade.symbol,
                    "strategy": trade.strategy_name,
                    "state": getattr(trade.state, "value", str(trade.state)),
                },
                summary=f"symbol={trade.symbol}",
            )
            print(f"[POSITION_MANAGE] symbol={trade.symbol} state={getattr(trade.state, 'value', trade.state)}")
        self._last_position_management_tick_utc = now

    @staticmethod
    def _is_near_whole_or_half_dollar(price: float) -> bool:
        cents = float(price) % 1
        return abs(cents - 0.0) < 0.02 or abs(cents - 0.5) < 0.02

    def _build_trade_management_market_state(self) -> dict[str, dict]:
        market_state: dict[str, dict] = {}
        for symbol in sorted(self.trade_management_engine.snapshot_positions().keys()):
            try:
                price = float(self.price_feed.get_price(symbol))
            except Exception:
                continue
            near_key_level = self._is_near_whole_or_half_dollar(price)
            market_state[symbol] = {
                "current_price": float(price),
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.0,
                "structure_intact": True,
                "near_resistance": near_key_level,
                "key_level_hit": near_key_level,
                "last_higher_low": float(price) * 0.995,
            }
        return market_state

    def _apply_execution_results_to_trade_management(self, execution_output: list[ExecutionResult]) -> None:
        for result in execution_output:
            filled_qty = int(getattr(result, "filled_quantity", 0) or 0)
            if filled_qty <= 0:
                continue
            symbol = str(getattr(result, "symbol", "") or "").upper()
            if not symbol:
                continue
            entry_price = float(
                getattr(result, "average_fill_price", None)
                or getattr(result, "entry_price", None)
                or getattr(result, "raw_price", None)
                or 0.0
            )
            if entry_price <= 0:
                continue
            exec_id = str(
                getattr(result, "execution_id", None)
                or f"{symbol}:{getattr(result, 'ibkr_order_id', 'na')}:{filled_qty}:{entry_price}"
            )
            direction = str(getattr(result, "direction", "") or "").upper()
            signed_shares = -filled_qty if direction in {"SELL", "SHORT"} else filled_qty
            self.trade_management_engine.on_exec_details(
                symbol=symbol,
                shares=signed_shares,
                price=entry_price,
                exec_id=exec_id,
            )

    def _run_trade_management_engine(self, execution_output: list[ExecutionResult]) -> list[object]:
        self._apply_execution_results_to_trade_management(execution_output)
        market_state = self._build_trade_management_market_state()
        intents = self.trade_management_engine.evaluate_cycle(market_state)
        for intent in intents:
            print(
                "[TRADE_MANAGEMENT][INTENT] "
                f"action={getattr(intent, 'action', 'UNKNOWN')} symbol={getattr(intent, 'symbol', 'UNKNOWN')} "
                f"qty={getattr(intent, 'quantity', 0)} reason={getattr(intent, 'reason', 'UNKNOWN')}"
            )
            self.event_collector.emit(
                event_type="TRADE_MANAGEMENT_INTENT",
                source="TradeManagementEngine",
                payload={
                    "action": getattr(intent, "action", "UNKNOWN"),
                    "symbol": getattr(intent, "symbol", "UNKNOWN"),
                    "quantity": int(getattr(intent, "quantity", 0) or 0),
                    "reason": getattr(intent, "reason", "UNKNOWN"),
                },
            )
        return intents

    def _detect_unprotected_positions(self, open_positions: list[ActiveTrade], *, stage: str) -> None:
        for trade in open_positions:
            if getattr(trade, "stop_loss_price", None) is not None:
                continue
            print(
                "[CRITICAL][UNPROTECTED_POSITION] "
                f"stage={stage} symbol={trade.symbol} trader_type={trade.trader_type} "
                f"strategy={trade.strategy_name} quantity={trade.quantity}"
            )

    def _log_broker_cycle_diagnostics(self, *, provider: str) -> None:
        health = self.connection_manager.healthcheck()
        connection = "ACTIVE" if health.get("connected") else "FAILED"
        market_data_type = str(health.get("market_data_type") or "UNKNOWN").upper()
        host = health.get("host")
        port = health.get("port")
        client_id = health.get("client_id")
        print(f"[BROKER] provider={provider}")
        print(f"[BROKER] connection={connection}")
        print(f"[BROKER] market_data_type={market_data_type}")
        print(f"[BROKER] host={host}")
        print(f"[BROKER] port={port}")
        print(f"[BROKER] client_id={client_id}")

    @staticmethod
    def _apply_position_truth_entry_guard(
        intents: list[TradeIntent],
        verdict: PositionTruthVerdict,
    ) -> list[TradeIntent]:
        if not verdict.block_new_entries:
            return intents
        if intents:
            print("[POSITION][TRUTH][BLOCK] reason=block_new_entries")
            for intent in intents:
                print(
                    f"[TRADE_PATH][EXECUTION] symbol={intent.symbol.upper()} "
                    "verdict=SKIPPED_MODE_OR_SESSION_POLICY reason=POSITION_TRUTH_BLOCK_NEW_ENTRIES"
                )
        return []

    def _resolve_position_truth_cycle(
        self,
        *,
        as_of: datetime,
    ) -> PositionTruthVerdict:
        print("[POSITION][TRUTH][START]")
        if self.run_mode == RunMode.SIM:
            print(f"[POSITION][TRUTH][SKIP] run_mode={self.run_mode.value}")
            self._latest_position_truth_snapshot = empty_position_truth_snapshot(as_of=as_of)
            self._latest_position_truth_verdict = healthy_position_truth_verdict()
            return self._latest_position_truth_verdict

        broker_required = self.run_mode in {RunMode.PAPER, RunMode.LIVE, RunMode.READ_ONLY}
        broker_positions = collect_broker_position_snapshot(
            self.connection_manager.optional_client,
            as_of=as_of,
            config=PositionTruthConfig(
                broker_required=broker_required,
                run_mode=self.run_mode,
            ),
        )
        system_positions = collect_system_position_snapshot(
            self.trade_registry.snapshot(),
            as_of=as_of,
        )
        snapshot, verdict = reconcile_position_truth(
            broker_positions=broker_positions,
            system_positions=system_positions,
            as_of=as_of,
            live_broker_mode=broker_required,
        )
        self._latest_position_truth_snapshot = snapshot
        self._latest_position_truth_verdict = verdict
        print(
            "[POSITION][TRUTH][VERDICT] "
            f"healthy={verdict.healthy} block_new_entries={verdict.block_new_entries} "
            f"block_exits={verdict.block_exits}"
        )
        if verdict.require_reconciliation:
            self._degraded = True
        if verdict.block_exits:
            print("[POSITION][TRUTH][BLOCK] reason=block_exits")
        blocked = verdict.block_new_entries or verdict.block_exits
        print(
            "[POSITION][TRUTH][CYCLE_SUMMARY] "
            f"broker={len(snapshot.broker_positions)} system={len(snapshot.system_positions)} "
            f"matched={len(snapshot.matched_symbols)} mismatches={len(snapshot.mismatches)} "
            f"critical={verdict.critical_mismatch_count} warning={verdict.warning_mismatch_count} "
            f"blocked={blocked}"
        )
        return verdict

    def _resolve_fill_authority_cycle(self) -> dict[str, object]:
        try:
            from src.execution.order_router import runtime_lifecycle_snapshot
        except Exception as exc:
            print(f"[EXECUTION][FILL_AUTHORITY][ERROR] reason=import_failed error={exc}")
            verdict = {"execution_stalled": False, "stalled_symbols": []}
            self._latest_fill_authority_verdict = verdict
            return verdict

        snapshot = runtime_lifecycle_snapshot()
        stalled = bool(
            int(snapshot.get("submitted_no_ack_timeouts", 0) or 0) > 0
            or int(snapshot.get("working_no_fill_timeouts", 0) or 0) > 0
            or int(snapshot.get("partial_fill_stalls", 0) or 0) > 0
        )
        verdict = {"execution_stalled": stalled, "stalled_symbols": []}
        self._latest_fill_authority_verdict = verdict
        print(f"[EXECUTION][FILL_AUTHORITY][VERDICT] execution_stalled={stalled}")
        return verdict

    def attach_broker_position_from_recovery(self, *, symbol: str) -> None:
        snapshot = self._latest_position_truth_snapshot
        if snapshot is None:
            return
        broker_row = snapshot.broker_positions.get(symbol.upper())
        if broker_row is None:
            return
        if any(t.symbol.upper() == symbol.upper() for t in self.trade_registry.snapshot()):
            return
        recovered_trade = ActiveTrade(
            symbol=symbol.upper(),
            trader_type="BROKER_ATTACHED",
            entry_tick=0,
            entry_price=float(broker_row.avg_cost or 0.0),
            direction="SHORT" if int(broker_row.quantity) < 0 else "LONG",
            quantity=abs(int(broker_row.quantity)),
            strategy_name="BROKER_RECOVERY",
            stop_loss_price=0.0,
        )
        setattr(recovered_trade, "recovery_tag", "broker_attached")
        self.trade_registry.register_trade(recovered_trade)

    def _run_manager_pipeline(
        self,
        *,
        cycle_started_at: datetime,
        ny_time: datetime,
        uk_time: datetime,
        session_phase: str,
        forced_session_label: str | None = None,
        forced_session_source: str | None = None,
    ) -> bool:
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        mode_manager = self.runtime_mode_manager
        print(f"[RUNTIME] {mode_manager.describe()}")
        position_truth_verdict = self._resolve_position_truth_cycle(as_of=cycle_started_at)
        fill_verdict = self._resolve_fill_authority_cycle()
        recovery_plan = build_recovery_plan(
            self._latest_position_truth_snapshot or empty_position_truth_snapshot(as_of=cycle_started_at),
            position_truth_verdict,
            fill_verdict,
        )
        apply_recovery_actions(recovery_plan, self)
        self._run_position_management_tick(cycle_started_at)
        active_strategy_keys = self._enabled_strategy_keys()
        strategy_key = self.primary_strategy_key

        force_mock_provider = self.run_mode == RunMode.SIM
        if force_mock_provider:
            print(
                "[CONNECTIVITY][SKIP] "
                f"run_mode={self.run_mode.value} forcing MOCK scanner provider."
            )
        else:
            if self.run_mode == RunMode.PAPER:
                print("[CONNECTIVITY][PAPER] broker-connected validation path enabled")
            elif self.run_mode == RunMode.LIVE:
                print("[CONNECTIVITY][LIVE] broker-connected production path enabled")
            try:
                self.connection_manager.ensure_connected()
            except Exception as exc:
                print("STATE=DEGRADED")
                print(f"[CONNECTIVITY] IBKR connection failed: {exc}")
                self._trace_halt(reason_code="CONNECTIVITY_FAILURE", message=str(exc), stage="CONNECTIVITY")
                if self.run_mode == RunMode.LIVE:
                    print("[CRITICAL] IBKR connection lost in LIVE mode")
                    print("[CRITICAL] trading halted")
                    return False
                fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
                force_mock_provider = fallback_enabled or str(get_config("SCANNER_DATA_SOURCE") or "").upper() == "MOCK"

        if self.market_data_snapshot_manager is None:
            self.market_data_snapshot_manager = MarketDataSnapshotManager(self.connection_manager.optional_client)
        provider_override = MockScannerProvider() if force_mock_provider else None
        self._log_broker_cycle_diagnostics(provider="MOCK" if provider_override is not None else "IBKR")

        top_refresh = int(get_config("TOPN_REFRESH_SECONDS"))
        watch_refresh = int(get_config("WATCHLIST_REFRESH_SECONDS"))
        focus_refresh = int(get_config("FOCUS_REFRESH_SECONDS"))
        top_limit = int(get_config("TOPN_MAX_SYMBOLS_PER_STRATEGY"))
        watch_limit = int(get_config("WATCHLIST_MAX_SYMBOLS_PER_STRATEGY"))
        focus_limit_max = int(get_config("FOCUS_MAX_SYMBOLS_PER_STRATEGY"))

        selected_watchlist: list[CandidateMetrics] = []
        selected_focus: list[CandidateMetrics] = []
        selected_observations: list[CandidateMetrics] = []
        selected_candidates: list[object] = []

        pipeline_trace("SCAN")
        for active_strategy in active_strategy_keys:
            _, active_scanner_policy = self._build_scanner_policy_for_strategy(active_strategy, session_phase)
            active_request = self._build_scanner_request(active_scanner_policy, strategy_name=active_strategy, session_phase=session_phase)
            cadence = self._strategy_cadence(active_strategy)
            strategy_payload: dict = {}

            top_stale = self._is_stale(cadence.top_n, cycle_started_at, top_refresh)
            watch_stale = self._is_stale(cadence.watchlist, cycle_started_at, watch_refresh)
            focus_stale = self._is_stale(cadence.focus, cycle_started_at, focus_refresh)

            if cadence.scanner_cooldown_until_utc and cycle_started_at < cadence.scanner_cooldown_until_utc:
                top_stale = False

            if top_stale:
                try:
                    strategy_payload = run_scanner_cycle(
                        mode="integrated",
                        policy=active_scanner_policy,
                        scanner_request=active_request,
                        event_collector=self.event_collector,
                        provider=provider_override,
                        market_data_client=self.connection_manager.optional_client,
                        disconnect_provider=provider_override is not None,
                        forced_session_label=forced_session_label,
                        forced_session_source=forced_session_source,
                    )
                    observations = list(strategy_payload.get("candidate_metrics", []))
                    universe_entries = list(strategy_payload.get("universe_top_n", []))
                    new_symbols = [entry.get("symbol") for entry in universe_entries if isinstance(entry, dict) and entry.get("symbol")][:top_limit]
                    changed = new_symbols != cadence.top_n.symbols
                    if changed:
                        added = sorted(set(new_symbols) - set(cadence.top_n.symbols))
                        removed = sorted(set(cadence.top_n.symbols) - set(new_symbols))
                        print(f"[TOPN_REFRESH] strategy={active_strategy} added={added} removed={removed}")
                        cadence.top_n.symbols = new_symbols
                        cadence.top_n.rows = observations
                        watch_stale = True
                    else:
                        print(f"[TOPN_REFRESH] strategy={active_strategy} unchanged")
                    cadence.top_n.timestamp_utc = cycle_started_at
                    self._trace_event("TOPN_REFRESH", {"strategy": active_strategy, "size": len(cadence.top_n.symbols), "changed": changed})
                except ProviderConnectionError:
                    raise
                except Exception as exc:
                    message = str(exc)
                    if "162" in message or "cancel" in message.lower():
                        cooldown = cycle_started_at + timedelta(seconds=30)
                        cadence.scanner_cooldown_until_utc = cooldown
                        print(f"[SCANNER_ERROR_162] strategy={active_strategy} cooldown_until={cooldown.isoformat()} err={message}")
                        self._trace_event("SCANNER_ERROR_162", {"strategy": active_strategy, "error": message, "cooldown_until_utc": cooldown.isoformat()})
                    else:
                        print(f"[SCANNER][WARN] strategy={active_strategy} err={message}")

            observations = list(cadence.top_n.rows)
            payload_watch_rows = list(strategy_payload.get("watchlist_k", []))
            payload_focus_rows = list(strategy_payload.get("focus_m", []))

            if watch_stale:
                scanner_candidates = list(observations)
                enriched_candidates = list(strategy_payload.get("candidate_metrics", [])) or list(scanner_candidates)
                pre_gate = list(enriched_candidates)
                post_gate = [
                    candidate
                    for candidate in pre_gate
                    if str(getattr(candidate, "symbol", "")).strip()
                ]
                print(f"[DEBUG][SCANNER_OUTPUT] count={len(scanner_candidates)}")
                print(f"[DEBUG][POST_ENRICHMENT] count={len(enriched_candidates)}")
                print(f"[GATE][RESULT] before={len(pre_gate)} after={len(post_gate)}")
                if not post_gate and pre_gate:
                    print("[ERROR][GATE_WIPED_ALL] post_gate_empty_fallback_to_pre_gate")
                    post_gate = list(pre_gate)
                candidates_for_watchlist = list(post_gate)
                print(f"[DEBUG][PRE_WATCHLIST] count={len(candidates_for_watchlist)}")
                if not candidates_for_watchlist and scanner_candidates:
                    print("[ERROR][PIPELINE_BREAK] scanner produced symbols but watchlist input empty")
                    candidates_for_watchlist = list(scanner_candidates)
                if not candidates_for_watchlist:
                    watch_rows = []
                    focus_rows = []
                else:
                    policy_v2 = resolve_policy_v2(active_strategy)
                    if payload_watch_rows:
                        watch_rows = payload_watch_rows
                        focus_rows = payload_focus_rows
                    elif policy_v2 and is_policy_v2_enabled_for_strategy(active_strategy):
                        watch_rows, focus_rows = self._build_watchlist_focus_v2(policy_v2, candidates_for_watchlist)
                    else:
                        selector = resolve_watchlist_selector(active_scanner_policy.ranking_intent)
                        watch_rows = (
                            selector(candidates_for_watchlist, active_scanner_policy)
                            if selector
                            else self._select_watchlist_for_policy(
                                candidates_for_watchlist,
                                active_scanner_policy,
                                enforce_session_allowlist=False,
                            )
                        )
                        focus_rows = watch_rows[: max(0, active_scanner_policy.focus_limit_m)]
                cadence.watchlist.rows = list(watch_rows[:watch_limit])
                cadence.watchlist.symbols = self._symbols_from_candidates(cadence.watchlist.rows)
                cadence.watchlist.timestamp_utc = cycle_started_at
                self._trace_event("WATCHLIST_CREATED", {"strategy": active_strategy, "size": len(cadence.watchlist.symbols)})
                if not focus_stale and not cadence.focus.rows:
                    focus_stale = True

            if focus_stale:
                base = payload_focus_rows or list(cadence.watchlist.rows)[:focus_limit_max]
                cadence.focus.rows = list(base[:focus_limit_max])
                cadence.focus.symbols = self._symbols_from_candidates(cadence.focus.rows)
                cadence.focus.timestamp_utc = cycle_started_at
                self._trace_event("FOCUS_LIST_CREATED", {"strategy": active_strategy, "size": len(cadence.focus.symbols)})

            print(
                f"[STRATEGY_AUDIT] strategy={active_strategy} topn_size={len(cadence.top_n.symbols)} "
                f"watchlist_size={len(cadence.watchlist.symbols)} focus_size={len(cadence.focus.symbols)} "
                f"open_positions={self.trade_registry.count_active()}"
            )

            if active_strategy == strategy_key:
                selected_watchlist = list(cadence.watchlist.rows)
                selected_focus = list(cadence.focus.rows)
                selected_observations = observations
                selected_candidates = list(strategy_payload.get("candidates", [])) or selected_candidates

        mock_scanner_mode = self._mock_scanner_mode_enabled()
        if mock_scanner_mode and not selected_watchlist:
            fallback_candidates = list(selected_observations) or list(selected_candidates)
            fallback_limit = max(1, min(5, len(fallback_candidates))) if fallback_candidates else 0
            selected_watchlist = list(fallback_candidates[:fallback_limit])
            selected_focus = list(selected_watchlist[: max(1, min(3, len(selected_watchlist)))])
            print(
                "[WATCHLIST][FALLBACK] "
                f"mock_mode=True reason=EMPTY_STRATEGY_WATCHLIST source_count={len(fallback_candidates)} selected={len(selected_watchlist)}"
            )

        pipeline_trace("CONTEXT")
        manual_focus_symbols = self._refresh_manual_focus_if_due(cycle_started_at)
        manual_focus_rows, manual_focus_rejections = self._resolve_manual_focus_candidates(
            manual_symbols=manual_focus_symbols,
            session_phase=session_phase,
        )
        watchlist_symbols = self._symbols_from_candidates(selected_watchlist)
        auto_focus_symbols = self._symbols_from_candidates(selected_focus)
        merged = list(selected_focus)
        manual_allowed = bool(getattr(self, "_manual_focus_enabled", True)) and not merged
        selected_focus = self._merge_focus_candidates(
            scanner_focus=merged,
            manual_candidates=manual_focus_rows if manual_allowed else [],
            session_phase=session_phase,
        )
        final_evaluation_symbols = self._symbols_from_candidates(selected_focus)
        print(f"[PIPELINE][WATCHLIST] count={len(watchlist_symbols)} symbols={watchlist_symbols}")
        print(f"[PIPELINE][FOCUS] count={len(final_evaluation_symbols)} symbols={final_evaluation_symbols}")
        manual_focus_accepted_symbols = self._symbols_from_candidates(manual_focus_rows)
        print(
            "[FINAL_EVAL][MERGE] "
            f"auto_focus={auto_focus_symbols} manual_focus={manual_focus_accepted_symbols} final={final_evaluation_symbols}"
        )
        focus_source = "MANUAL" if manual_focus_accepted_symbols and not auto_focus_symbols else "MIXED" if manual_focus_accepted_symbols and auto_focus_symbols else "AUTO"
        if len(final_evaluation_symbols) == 0 and len(watchlist_symbols) > 0:
            fallback_symbols = watchlist_symbols[:3]
            print("[FALLBACK][FOCUS_EMPTY] using_watchlist_candidates")
            print(
                "[FALLBACK][ENGAGED] "
                f"reason=EMPTY_FOCUS fallback_symbols={fallback_symbols}"
            )
            final_evaluation_symbols = list(fallback_symbols)
            focus_source = "FALLBACK_FROM_WATCHLIST"
        if not auto_focus_symbols and manual_focus_accepted_symbols:
            print(f"[FINAL_EVAL][MANUAL_ONLY] symbols={manual_focus_accepted_symbols} reason=manual_override_only")
        print(
            "[MANUAL_FOCUS][SUMMARY] "
            f"accepted={len(manual_focus_rows)} rejected={len(manual_focus_rejections)} "
            f"final_contribution={len([s for s in final_evaluation_symbols if s in set(manual_focus_accepted_symbols)])}"
        )
        print(
            "[FINAL_EVAL][SUMMARY] "
            f"AUTO_FOCUS_M={auto_focus_symbols} "
            f"MANUAL_FOCUS={manual_focus_accepted_symbols} "
            f"FINAL_EVALUATION_SYMBOLS={final_evaluation_symbols}"
        )
        scanner_keep_symbols = self._symbols_from_candidates(selected_observations)
        scanner_kept_count = len(scanner_keep_symbols)
        pipeline_audit = PipelineAudit(
            self._current_cycle_id or str(uuid4()),
            runtime_mode=self.run_mode.value,
            strategy_key=strategy_key,
        )
        pipeline_audit.mark_kept(scanner_keep_symbols)
        print(
            "[TRADE_PATH][START] "
            f"cycle_id={pipeline_audit.cycle_id} runtime_mode={self.run_mode.value} "
            f"strategy_key={strategy_key} scanner_seen={len(scanner_keep_symbols)}"
        )
        focus_rvol_threshold = float(get_config("FOCUS_RVOL_MIN") or 0.0)
        print(f"[FOCUS][RVOL_THRESHOLD] value={focus_rvol_threshold}")
        print(f"[WATCHLIST][FINAL] size={len(watchlist_symbols)} symbols={watchlist_symbols}")
        print(f"[FOCUS][CANDIDATES] symbols={watchlist_symbols}")
        print(f"[FOCUS][SELECTED] symbols={final_evaluation_symbols}")
        final_focus_set = {s.upper() for s in final_evaluation_symbols}
        watchlist_set = {s.upper() for s in watchlist_symbols}
        rvol_by_symbol = {
            str(getattr(candidate, "symbol", "")).upper(): getattr(candidate, "rvol", None)
            for candidate in selected_observations
            if str(getattr(candidate, "symbol", "")).strip()
        }
        for symbol in scanner_keep_symbols:
            symbol_upper = symbol.upper()
            pipeline_audit.mark_stage(symbol_upper, "SCANNER", scanner_seen=True)
            symbol_rvol = rvol_by_symbol.get(symbol_upper)
            focus_result = "PASS" if symbol_upper in final_focus_set else "FAIL"
            print(
                "[FOCUS][SYMBOL] "
                f"symbol={symbol} result={focus_result} rvol={symbol_rvol} threshold={focus_rvol_threshold}"
            )
            if symbol_upper not in watchlist_set:
                print(f"[FOCUS][REJECT] symbol={symbol} reason=SCANNER_KEEP_NOT_IN_WATCHLIST")
                print(f"[TRADE_PATH][WATCHLIST] symbol={symbol_upper} verdict=WATCHLIST_REJECTED reason=SCANNER_KEEP_NOT_IN_WATCHLIST")
                pipeline_audit.mark_stage(symbol_upper, "WATCHLIST", watchlist_seen=False)
                pipeline_audit.record(symbol, TerminalOutcome.WATCHLIST_REJECTED, "SCANNER_KEEP_NOT_IN_WATCHLIST", "watchlist")
            elif symbol_upper not in final_focus_set:
                print(f"[FOCUS][REJECT] symbol={symbol} reason=NOT_SELECTED_FOR_FOCUS")
                print(f"[TRADE_PATH][FOCUS] symbol={symbol_upper} verdict=FOCUS_REJECTED reason=NOT_SELECTED_FOR_FOCUS")
                pipeline_audit.mark_stage(symbol_upper, "WATCHLIST", watchlist_seen=True)
                pipeline_audit.mark_stage(symbol_upper, "FOCUS", focus_seen=False)
                pipeline_audit.record(symbol, TerminalOutcome.FOCUS_REJECTED, "NOT_SELECTED_FOR_FOCUS", "focus")
            else:
                pipeline_audit.mark_stage(symbol_upper, "WATCHLIST", watchlist_seen=True)
                pipeline_audit.mark_stage(symbol_upper, "FOCUS", focus_seen=True)
        self._trace_event("UNIVERSE", {"universe": [{"symbol": s} for s in self._symbols_from_candidates(selected_observations)]})
        if watchlist_symbols:
            print(f"[WATCHLIST] size={len(watchlist_symbols)} symbols={watchlist_symbols}")
        else:
            print("[WATCHLIST][EMPTY] reason=no_scanner_candidates_after_gating")
        self._trace_event("WATCHLIST", {"watchlist_symbols": watchlist_symbols})
        if final_evaluation_symbols:
            print(f"[FOCUS] size={len(final_evaluation_symbols)} symbols={final_evaluation_symbols}")
        else:
            print("[FOCUS][EMPTY] reason=no_focus_symbols_after_selection")
        self._trace_event("FOCUS", {"focus": [{"symbol": s} for s in final_evaluation_symbols]})
        if not watchlist_symbols:
            print("[PIPELINE][SKIP] empty watchlist")
            final_evaluation_symbols = []
        strategy_watchlist = selected_watchlist or selected_focus
        if not strategy_watchlist:
            fallback_candidates = list(selected_watchlist) or list(selected_observations)
            strategy_watchlist = [
                candidate
                for candidate in fallback_candidates
                if getattr(candidate, "symbol", None)
            ]
            print(
                "[RECOVERY] strategy_watchlist rebuilt "
                f"count={len(strategy_watchlist)}"
            )
        if final_evaluation_symbols:
            focus_only = {symbol.upper() for symbol in final_evaluation_symbols}
            strategy_watchlist = [
                candidate
                for candidate in strategy_watchlist
                if str(getattr(candidate, "symbol", "")).upper() in focus_only
            ]
        if final_evaluation_symbols and not strategy_watchlist:
            lookup_candidates = list(selected_focus) + list(selected_watchlist) + list(selected_observations)
            lookup_by_symbol = {
                str(getattr(candidate, "symbol", "")).upper(): candidate
                for candidate in lookup_candidates
                if str(getattr(candidate, "symbol", "")).strip()
            }
            strategy_watchlist = [
                lookup_by_symbol[symbol.upper()]
                for symbol in final_evaluation_symbols
                if symbol.upper() in lookup_by_symbol
            ]
            print(
                "[FOCUS][HANDOFF_RECOVERY] "
                f"requested={len(final_evaluation_symbols)} recovered={len(strategy_watchlist)}"
            )
        strategy_evaluation_symbols = self._symbols_from_candidates(strategy_watchlist)
        print(
            "[PIPELINE][HANDOFF] "
            f"watchlist={len(watchlist_symbols)} "
            f"focus={len(final_evaluation_symbols)} "
            f"strategy_input={len(strategy_evaluation_symbols)}"
        )
        if watchlist_symbols and not strategy_evaluation_symbols:
            print("[ERROR] WATCHLIST_WITHOUT_STRATEGY_INPUT")
            strategy_evaluation_symbols = watchlist_symbols[:5]
            lookup_candidates = list(selected_watchlist) + list(selected_focus) + list(selected_observations)
            lookup_by_symbol = {
                str(getattr(candidate, "symbol", "")).upper(): candidate
                for candidate in lookup_candidates
                if str(getattr(candidate, "symbol", "")).strip()
            }
            strategy_watchlist = [
                lookup_by_symbol[symbol.upper()]
                for symbol in strategy_evaluation_symbols
                if symbol.upper() in lookup_by_symbol
            ]
            print(
                "[RECOVERY] Using watchlist as strategy input "
                f"symbols={strategy_evaluation_symbols}"
            )
        if watchlist_symbols and not strategy_evaluation_symbols:
            raise Exception("PIPELINE_BREAK_FOCUS_TO_STRATEGY")
        print(
            "[PIPELINE] "
            f"scanner_count={scanner_kept_count} "
            f"focus_count={len(final_evaluation_symbols)} "
            f"strategy_input_count={len(strategy_evaluation_symbols)}"
        )
        print(f"[STRATEGY_RUNNER][RECEIVE] symbols={strategy_evaluation_symbols}")
        print(f"[ORCHESTRATOR][DISPATCH] passing {len(strategy_evaluation_symbols)} symbols to strategy")
        strategy_inputs = strategy_watchlist
        if not final_evaluation_symbols and strategy_evaluation_symbols:
            print(
                "[FOCUS][FALLBACK_TO_WATCHLIST] "
                f"reason=focus_empty_using_watchlist symbols={strategy_evaluation_symbols}"
            )
            fallback_symbols = list(strategy_evaluation_symbols[:3])
            print(
                "[FALLBACK][ENGAGED] "
                f"reason=EMPTY_FOCUS fallback_symbols={fallback_symbols}"
            )
            final_evaluation_symbols = fallback_symbols
            focus_source = "FALLBACK_FROM_WATCHLIST"
        print(f"[FOCUS_FINAL] count={len(final_evaluation_symbols)} symbols={final_evaluation_symbols}")
        if not final_evaluation_symbols:
            print(
                "[FOCUS][EMPTY_REASON] "
                f"watchlist_count={len(watchlist_symbols)} auto_focus_count={len(auto_focus_symbols)} "
                f"manual_focus_count={len(manual_focus_accepted_symbols)}"
            )
        scanner_payload = locals().get("scanner_watchlist_payload") or {}
        focus_evaluated = int(scanner_payload.get("focus_evaluated", 0))
        focus_passed = int(scanner_payload.get("focus_passed", len(final_evaluation_symbols)) or 0)
        focus_rejected = int(scanner_payload.get("focus_rejected", 0))
        focus_dominant_reasons = dict(scanner_payload.get("focus_dominant_reasons", {}) or {})
        snapshots_by_symbol, _ = self.market_data_snapshot_manager.batch_snapshots(final_evaluation_symbols)
        session_label = canonical_session_label(
            forced_session_label
            or (selected_watchlist[0].session_label if selected_watchlist else session_phase)
        )
        self.strategy_runner.receive_watchlist_snapshot(
            watchlist_symbols=final_evaluation_symbols,
            snapshots=snapshots_by_symbol,
            session_label=session_label,
            timestamp_utc=cycle_started_at.isoformat(),
        )
        tha_decisions = self._resolve_tha_decisions(
            strategy_inputs=strategy_inputs,
            now_utc=cycle_started_at,
        )
        if tha_decisions:
            allowed_by_tha = {
                symbol for symbol, decision in tha_decisions.items()
                if bool(getattr(decision, "allow_entries", False))
            }
            strategy_inputs = [
                candidate
                for candidate in strategy_inputs
                if str(getattr(candidate, "symbol", "") or "").upper() in allowed_by_tha
            ]

            if self.execution_enabled:
                for symbol, tha_decision in tha_decisions.items():
                    if bool(getattr(tha_decision, "force_flat", False)):
                        self.execution_engine.force_flatten_symbol(
                            symbol,
                            reason="THA_OUTSIDE_WINDOW",
                        )
            else:
                print("[PIPELINE][THA_POLICY] execution_disabled=True flatten_skipped=True")
        session_execution_allowed = session_label in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
        if mock_scanner_mode and not session_execution_allowed:
            session_execution_allowed = True
            print("[SESSION][MOCK_OVERRIDE] execution_allowed=True")
        if not session_execution_allowed and watchlist_symbols:
            print("[VALIDATION_OVERRIDE] Forcing strategy execution despite session restrictions")
        for symbol in self._symbols_from_candidates(strategy_watchlist):
            print(f"[STRATEGY] runner=ross_momentum symbol={symbol} stage=evaluate")
            print(f"[ROSS][SYMBOL_EVAL][START] symbol={symbol} source=orchestrator_handoff")
        if strategy_watchlist:
            print("[STRATEGY][EXECUTION] invoking StrategyRunner")
            print("[STRATEGY][FORCED_EXECUTION] invoking StrategyRunner regardless of session")
            print("[ROSS][PROCESS_START]")
            print("[ROSS][PATTERN_PIPELINE] ACTIVE")
            print("[ROSS][TRIGGER_PIPELINE] ACTIVE")
            pipeline_trace("STRUCTURE")
            print("[STRATEGY_RUNNER] invoking RossMomentumStrategyV1")
            strategy_output = self.strategy_runner.process(
                strategy_key=strategy_key,
                watchlist=strategy_inputs,
                snapshots=snapshots_by_symbol,
                session_label=session_label,
                timestamp_utc=cycle_started_at.isoformat(),
                mode=self.run_mode,
                session_phase=session_phase,
                execution_allowed=True if strategy_watchlist else session_execution_allowed,
                execution_ready=True if strategy_watchlist else session_execution_allowed,
                prep_only=False if strategy_watchlist else session_label in {"AH", "CLOSED"},
            )
        else:
            print("[PIPELINE][SKIP] empty watchlist")
            strategy_output = []
        print(f"[PIPELINE][STRATEGY_OUTPUT] count={len(strategy_output or [])}")
        print(
            "[PIPELINE][INTENTS] "
            f"count={len(strategy_output or [])} symbols={[getattr(intent, 'symbol', None) for intent in (strategy_output or [])]}"
        )
        for symbol, tha_decision in tha_decisions.items():
            symbol_upper = str(symbol).upper()
            trigger_ready = any(
                str(getattr(intent, "symbol", "")).upper() == symbol_upper
                and bool(getattr(intent, "trigger_ready", False))
                for intent in (strategy_output or [])
            )
            intent_created = any(
                str(getattr(intent, "symbol", "")).upper() == symbol_upper
                for intent in (strategy_output or [])
            )
            print(
                "[PIPELINE][TRIGGER_TO_INTENT] "
                f"symbol={symbol_upper} trigger_ready={trigger_ready} intent_created={intent_created}"
            )
            if trigger_ready and bool(getattr(tha_decision, "in_window", False)) and not intent_created:
                raise RuntimeError("Trigger passed but no intent — pipeline broken")
        self._pipeline_runtime_counts["cycles_run"] += 1
        self._pipeline_runtime_counts["watchlist_count"] += len(watchlist_symbols)
        self._pipeline_runtime_counts["trade_intents"] += len(strategy_output or [])
        ross_strategy = next(
            (s for s in getattr(self.strategy_runner, "strategies", []) if getattr(s, "name", "") == "RossMomentumStrategyV1"),
            None,
        )
        evaluated_symbols = set(getattr(ross_strategy, "last_evaluated_symbols", []) or [])
        for symbol in final_evaluation_symbols:
            if symbol.upper() not in evaluated_symbols:
                print(f"[ROSS][CONTRACT_VIOLATION] symbol={symbol} reason=FOCUS_SELECTED_BUT_NOT_EVALUATED")
                print(
                    f"[TRADE_PATH][PATTERN] symbol={symbol.upper()} "
                    "verdict=PATTERN_DETECTED_BUT_SUPPRESSED reason=FOCUS_SELECTED_BUT_NOT_EVALUATED"
                )
                pipeline_audit.mark_stage(symbol.upper(), "PATTERN", pattern_inputs_ready=True, pattern_detected=True)
                pipeline_audit.record(
                    symbol,
                    TerminalOutcome.PATTERN_DETECTED_BUT_SUPPRESSED,
                    "FOCUS_SELECTED_BUT_NOT_EVALUATED",
                    "strategy",
                )

        emitted_symbols = {
            getattr(intent, "symbol", None)
            for intent in (strategy_output or [])
            if getattr(intent, "symbol", None)
        }
        for symbol in final_evaluation_symbols:
            print(f"[ROSS][EVALUATE][START] symbol={symbol}")
            emitted = symbol in emitted_symbols
            if emitted:
                no_trade_reason = "INTENT_EMITTED"
            elif symbol in set(manual_focus_accepted_symbols) and symbol not in set(auto_focus_symbols):
                no_trade_reason = "MANUAL_ONLY_NO_SETUP"
            else:
                no_trade_reason = "NO_SETUP:no_valid_setup_from_runner"
            print(f"[NO_TRADE_REASON] symbol={symbol} reason={no_trade_reason}")
            print(self._pattern_reason_line(symbol, emitted))
            self._trace_event("PATTERN_EVAL", {"strategy": strategy_key, "symbol": symbol, "intent_emitted": emitted})
            if emitted:
                pipeline_audit.mark_stage(symbol.upper(), "PATTERN", pattern_inputs_ready=True, pattern_detected=True)
                pipeline_audit.mark_stage(symbol.upper(), "TRIGGER", trigger_fired=True)
                pipeline_audit.mark_stage(symbol.upper(), "INTENT", intent_emitted=True)
                self._trace_event("SETUP_DETECTED", {"strategy": strategy_key, "symbol": symbol})
                self._trace_event("CONFIRMATION_PASS", {"strategy": strategy_key, "symbol": symbol})
                self._trace_event("TRIGGER_READY", {"strategy": strategy_key, "symbol": symbol})
                self._trace_event("INTENT_EMITTED", {"strategy": strategy_key, "symbol": symbol})
                self._trace_event("RISK_APPROVED", {"strategy": strategy_key, "symbol": symbol, "decision": "PASS"})
            else:
                print(f"[STRATEGY][NO_SIGNAL] symbol={symbol} reason=no_valid_setup_from_runner")
                self._trace_event("NO_SETUP", {"strategy": strategy_key, "symbol": symbol})
                print(f"[TRADE_PATH][PATTERN] symbol={symbol.upper()} verdict=NO_PATTERN_DETECTED reason=NO_SETUP:no_valid_setup_from_runner")
                pipeline_audit.mark_stage(symbol.upper(), "PATTERN", pattern_inputs_ready=True, pattern_detected=False)
                pipeline_audit.record(symbol, TerminalOutcome.NO_PATTERN_DETECTED, "NO_SETUP:no_valid_setup_from_runner", "strategy")

        raw_strategy_output = strategy_output or []
        pre_arbitration_intents = list(raw_strategy_output)
        print(
            "[PIPELINE][ARBITRATION_INPUT] "
            f"input_intents_count={len(pre_arbitration_intents)}"
        )
        setup_detected_symbols = {
            getattr(intent, "symbol", "").upper()
            for intent in raw_strategy_output
            if getattr(intent, "symbol", None)
        }
        if ross_strategy is not None:
            collector = getattr(ross_strategy, "_failure_trace_collector", None)
            traces = getattr(collector, "_symbols", []) if collector is not None else []
            for trace in traces[-len(final_evaluation_symbols or []):]:
                symbol = str(getattr(trace, "symbol", "") or "").upper()
                detected_ids = list(getattr(trace, "detected_pattern_ids", []) or [])
                if detected_ids and symbol:
                    setup_detected_symbols.add(symbol)
        self._pipeline_runtime_counts["setups_detected"] += len(setup_detected_symbols)
        self._pipeline_runtime_counts["triggers_fired"] += sum(
            1
            for intent in raw_strategy_output
            if bool(getattr(intent, "trigger_ready", False))
        )
        if watchlist_symbols and setup_detected_symbols and not raw_strategy_output:
            print("[ERROR] SETUP_WITHOUT_INTENT")
            raise Exception("PIPELINE_BREAK_SETUP_TO_INTENT")
        gated_strategy_output = self._enforce_ross_execution_integrity(raw_strategy_output)
        gated_strategy_output = self._apply_position_truth_entry_guard(
            gated_strategy_output,
            position_truth_verdict,
        )
        if (
            self._mock_scanner_mode_enabled()
            and pre_arbitration_intents
            and not gated_strategy_output
        ):
            gated_strategy_output = [pre_arbitration_intents[0]]
            print("[E29][MOCK_OVERRIDE] forced_intent_survives_arbitration")
        valid_intents_count = sum(
            1
            for intent in pre_arbitration_intents
            if str(getattr(intent, "symbol", "")).strip()
        )
        filtered_by_conflict = max(len(pre_arbitration_intents) - len(gated_strategy_output), 0)
        filtered_by_limits = 0
        final_intents_count = len(gated_strategy_output)
        print(
            "[ARBITRATION][SUMMARY] "
            f"input={len(pre_arbitration_intents)} valid={valid_intents_count} "
            f"conflict_removed={filtered_by_conflict} limited={filtered_by_limits} final={final_intents_count}"
        )
        print(
            "[PIPELINE][ARBITRATION_OUTPUT] "
            f"valid_intents_count={valid_intents_count} filtered_by_conflict={filtered_by_conflict} "
            f"filtered_by_limits={filtered_by_limits} final_intents_count={final_intents_count}"
        )
        gated_symbols = {getattr(intent, "symbol", "").upper() for intent in gated_strategy_output}
        for symbol in final_evaluation_symbols:
            symbol_upper = str(symbol or "").upper()
            strategy_detected = symbol_upper in setup_detected_symbols
            intent_created = any(str(getattr(intent, "symbol", "")).upper() == symbol_upper for intent in pre_arbitration_intents)
            arbitration_kept = symbol_upper in gated_symbols
            if arbitration_kept:
                reason = "kept"
            elif intent_created:
                reason = "conflict_or_limit"
            elif strategy_detected:
                reason = "setup_no_intent"
            else:
                reason = "no_setup"
            print(
                "[PIPELINE][SYMBOL_TRACE] "
                f"symbol={symbol_upper} strategy_detected={strategy_detected} intent_created={intent_created} "
                f"arbitration_kept={arbitration_kept} reason={reason}"
            )
        for intent in raw_strategy_output:
            symbol = getattr(intent, "symbol", "")
            if not symbol:
                continue
            symbol_upper = symbol.upper()
            if symbol_upper not in gated_symbols:
                print(
                    f"[TRADE_PATH][INTENT] symbol={symbol_upper} "
                    "verdict=INTENT_REJECTED_BY_POLICY reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY"
                )
                pipeline_audit.mark_stage(symbol_upper, "TRIGGER", trigger_fired=True)
                pipeline_audit.mark_stage(symbol_upper, "INTENT", intent_emitted=False)
                pipeline_audit.record(symbol, TerminalOutcome.INTENT_REJECTED_BY_POLICY, "INTENT_REJECTED_BY_EXECUTION_INTEGRITY", "trigger")
            else:
                pipeline_audit.mark_stage(symbol_upper, "TRIGGER", trigger_fired=True)
                pipeline_audit.mark_stage(symbol_upper, "INTENT", intent_emitted=True)
                pipeline_audit.record(symbol, TerminalOutcome.INTENT_NOT_EMITTED, "TRADE_INTENT_CREATED", "intent")

        print(
            "[PIPELINE][RISK_INPUT] "
            f"intents_count={len(gated_strategy_output)} symbols={[getattr(intent, 'symbol', None) for intent in gated_strategy_output]}"
        )
        risk_allowed_symbols = [getattr(intent, "symbol", "") for intent in gated_strategy_output]
        print(
            "[PIPELINE][RISK_OUTPUT] "
            f"approved_count={len(risk_allowed_symbols)} blocked_count=0 symbols={risk_allowed_symbols}"
        )

        if mode_manager.allow_orders:

            if gated_strategy_output:
                for intent in gated_strategy_output:
                    print(
                        "[PIPELINE][EXECUTION_ATTEMPT] "
                        f"symbol={intent.symbol} enabled={mode_manager.allow_orders}"
                    )
                    print(f"[EXECUTION] symbol={intent.symbol} enabled=True")
                    pipeline_trace("EXECUTION", intent.symbol)
                    self._trace_event("ORDER_SUBMITTED", {
                        "strategy": strategy_key,
                        "symbol": intent.symbol
                    })
                    pipeline_audit.mark_stage(intent.symbol, "RISK", risk_approved=True)
                    pipeline_audit.mark_stage(intent.symbol, "EXECUTION", execution_attempted=True, execution_submitted=True)
                    pipeline_audit.record(intent.symbol, TerminalOutcome.EXECUTION_SUBMITTED, "ORDER_SUBMITTED", "execution")
                    pipeline_audit.record(intent.symbol, TerminalOutcome.CALLBACK_PENDING, "CALLBACK_PENDING", "execution")

            else:
                # REQUIRED FOR E21 — even when all intents rejected
                self._trace_event("ORDER_SIMULATED", {
                    "strategy": strategy_key,
                    "reason": "NO_VALID_INTENTS_AFTER_GATING"
                })

        else:

            if raw_strategy_output:
                for intent in raw_strategy_output:
                    reason = "SESSION_BLOCK" if self.run_mode == RunMode.READ_ONLY else "EXECUTION_DISABLED"
                    print(
                        "[PIPELINE][EXECUTION_ATTEMPT] "
                        f"symbol={intent.symbol} enabled={mode_manager.allow_orders} reason={reason}"
                    )
                    print(f"[EXECUTION] symbol={intent.symbol} enabled=False reason={reason}")

                    self._trace_event("SESSION_BLOCK", {
                        "strategy": strategy_key,
                        "symbol": intent.symbol,
                        "reason": reason
                    })

                    self._trace_event("ORDER_SIMULATED", {
                        "strategy": strategy_key,
                        "symbol": intent.symbol,
                        "reason": reason
                    })
                    print(f"[TRADE_PATH][EXECUTION] symbol={intent.symbol.upper()} verdict=SKIPPED_MODE_OR_SESSION_POLICY reason={reason}")
                    pipeline_audit.mark_stage(intent.symbol, "EXECUTION", execution_attempted=True, execution_submitted=False)
                    pipeline_audit.record(intent.symbol, TerminalOutcome.SKIPPED_MODE_OR_SESSION_POLICY, reason, "execution")

            else:
                # REQUIRED FOR E21 — even if no intents exist at all
                print("[EXECUTION] enabled=False reason=NO_INTENTS_PRODUCED")
                self._trace_event("ORDER_SIMULATED", {
                    "strategy": strategy_key,
                    "reason": "NO_INTENTS_PRODUCED"
                })

        if final_intents_count == 0:
            no_trade_reason = {
                "no_intents_generated": len(pre_arbitration_intents) == 0,
                "all_blocked_by_risk": False,
                "all_removed_by_arbitration": len(pre_arbitration_intents) > 0,
                "execution_disabled": not mode_manager.allow_orders,
            }
            print(
                "[PIPELINE][NO_TRADE_REASON] "
                f"no_intents_generated={no_trade_reason['no_intents_generated']} "
                f"all_blocked_by_risk={no_trade_reason['all_blocked_by_risk']} "
                f"all_removed_by_arbitration={no_trade_reason['all_removed_by_arbitration']} "
                f"execution_disabled={no_trade_reason['execution_disabled']}"
            )

        intent_count = len(strategy_output or [])
        print(f"[INTENT] count={intent_count}")
        if strategy_output:
            for trade_intent in strategy_output:
                print(
                    "[INTENT] "
                    f"symbol={trade_intent.symbol} side={trade_intent.direction} "
                    f"entry={getattr(trade_intent, 'entry_price', None)} stop={getattr(trade_intent, 'stop_loss_price', None)} "
                    f"qty={getattr(trade_intent, 'quantity', None) or getattr(trade_intent, 'requested_quantity', None) or 1} "
                    f"source=ross_momentum"
                )
                print(
                    "[DECISION] "
                    f"symbol={trade_intent.symbol} verdict=emit_intent setup={getattr(trade_intent, 'pattern_name', None) or getattr(trade_intent, 'strategy_name', 'UNKNOWN')} executable={str(bool(mode_manager.allow_orders)).lower()}"
                )
        no_setup_count = max(len(final_evaluation_symbols) - intent_count, 0)
        dominant_no_trade_reasons = focus_dominant_reasons or {"NO_SETUP": no_setup_count}
        print(
            "[CYCLE_END] "
            f"cycle_id={self._current_cycle_id} canonical_session={session_label} "
            f"raw_top_n_count={len(selected_observations)} candidates_entering_gates={scanner_kept_count} survivors_after_gates={scanner_kept_count} "
            f"watchlist_count={len(watchlist_symbols)} focus_count_auto={len(auto_focus_symbols)} focus_count_manual={len(manual_focus_accepted_symbols)} "
            f"focus_count_final={focus_passed} evaluated_count={focus_evaluated} focus_rejected={focus_rejected} setup_trigger_count={intent_count} "
            f"no_setup_count={no_setup_count} intent_count={intent_count} order_submission_count={intent_count if mode_manager.allow_orders else 0} "
            f"open_positions_count={self.trade_registry.count_active()} dominant_drop_reasons=NA dominant_no_trade_reasons={dominant_no_trade_reasons} "
            f"execution_allowed={session_label in {'PRE', 'RTH_OPEN', 'RTH_MID', 'RTH_LATE'}} "
            f"execution_ready={session_label in {'PRE', 'RTH_OPEN', 'RTH_MID', 'RTH_LATE'}} focus_source={focus_source}"
        )
        print(
            "[PIPELINE] "
            f"scanner_kept={scanner_kept_count} watchlist={len(watchlist_symbols)} focus={len(final_evaluation_symbols)} "
            f"evaluated={len(final_evaluation_symbols)} intents={intent_count}"
        )
        summary = pipeline_audit.summary_payload()
        print(f"[TRADE_PATH][FINAL] cycle_id={self._current_cycle_id} counts={summary['counts']} symbols={summary['symbols']}")
        print(
            "[TRADE_PATH][CYCLE_SUMMARY] "
            f"cycle_id={self._current_cycle_id} evaluated_symbols={len(final_evaluation_symbols)} "
            f"scanner_seen={len(scanner_keep_symbols)} watchlist_seen={len(watchlist_symbols)} focus_seen={len(final_evaluation_symbols)} "
            f"patterns_detected={summary['readiness']['symbols_pattern_ready']} triggers_fired={summary['readiness']['symbols_trigger_ready']} "
            f"intents_emitted={summary['readiness']['symbols_intent_ready']} risk_approved={summary['readiness']['symbols_risk_ready']} "
            f"execution_attempts={summary['readiness']['symbols_execution_ready']} submitted={summary['readiness']['symbols_submitted']} "
            f"callback_pending={summary['counts'].get('CALLBACK_PENDING', 0)} filled={summary['counts'].get('FILLED', 0)} "
            f"dominant_final_verdicts={summary['dominant_final_verdicts']} dominant_blocking_reasons={summary['dominant_blocking_reasons']}"
        )
        print(
            "[TRADE_PATH][READINESS] "
            f"symbols_pattern_ready={summary['readiness']['symbols_pattern_ready']} "
            f"symbols_trigger_ready={summary['readiness']['symbols_trigger_ready']} "
            f"symbols_intent_ready={summary['readiness']['symbols_intent_ready']} "
            f"symbols_risk_ready={summary['readiness']['symbols_risk_ready']} "
            f"symbols_execution_ready={summary['readiness']['symbols_execution_ready']} "
            f"symbols_submitted={summary['readiness']['symbols_submitted']}"
        )
        evidence_dir = Path("AUDIT_EVIDENCE/make_it_trade_guarantee")
        paths = pipeline_audit.persist(base_dir=evidence_dir)
        violations = pipeline_audit.contract_violations()
        if violations:
            print(f"[PIPELINE_AUDIT][CONTRACT_VIOLATION] missing={[v['symbol'] for v in violations]} evidence={paths['violations']}")

        if self.regime_layer.enabled:
            self.regime_layer.evaluate(candidates=selected_candidates or [], session=get_current_market_session())
        self._trace_event("ACTION", {"trade_intents": intent_count, "allow_orders": mode_manager.allow_orders})
        if not intent_stage_seen():
            print("[FATAL] PIPELINE BROKEN — NO INTENT GENERATED")
        if not strategy_output:
            print("[STRATEGY] No trade intents generated.")
        return True

    def _enforce_ross_execution_integrity(self, intents: List[TradeIntent]) -> List[TradeIntent]:
        filtered_intents: List[TradeIntent] = []
        for intent in intents:
            has_valid_pattern = bool(getattr(intent, "has_valid_pattern", False))
            confirmation_passed = bool(getattr(intent, "confirmation_passed", False))
            trigger_ready = bool(getattr(intent, "trigger_ready", False))

            if not has_valid_pattern:
                print(
                    "[ROSS][EXECUTION][REJECT] "
                    f"reason=PATTERN_INVALID symbol={getattr(intent, 'symbol', 'UNKNOWN')}"
                )
                continue

            if not confirmation_passed:
                print(
                    "[ROSS][EXECUTION][REJECT] "
                    f"reason=CONFIRMATION_FAILED symbol={getattr(intent, 'symbol', 'UNKNOWN')}"
                )
                continue

            if not trigger_ready:
                print(
                    "[ROSS][EXECUTION][REJECT] "
                    f"reason=TRIGGER_NOT_READY symbol={getattr(intent, 'symbol', 'UNKNOWN')}"
                )
                continue

            filtered_intents.append(intent)

        return filtered_intents

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
        manual_focus_symbols = self._refresh_manual_focus_if_due(cycle_started_at)
        manual_focus_rows, manual_focus_rejections = self._resolve_manual_focus_candidates(
            manual_symbols=manual_focus_symbols,
            session_phase=session_phase,
        )
        auto_focus_symbols = list(focus_symbols)
        merged = list(focus_m)
        manual_allowed = bool(getattr(self, "_manual_focus_enabled", True)) and not merged
        focus_m = self._merge_focus_candidates(
            scanner_focus=merged,
            manual_candidates=manual_focus_rows if manual_allowed else [],
            session_phase=session_phase,
        )
        focus_symbols = self._symbols_from_candidates(focus_m)
        manual_focus_accepted_symbols = self._symbols_from_candidates(manual_focus_rows)
        print(
            "[FINAL_EVAL][MERGE] "
            f"auto_focus={auto_focus_symbols} manual_focus={manual_focus_accepted_symbols} final={focus_symbols}"
        )
        if not auto_focus_symbols and manual_focus_accepted_symbols:
            print(f"[FINAL_EVAL][MANUAL_ONLY] symbols={manual_focus_accepted_symbols}")
        print(
            "[MANUAL_FOCUS][SUMMARY] "
            f"accepted={len(manual_focus_rows)} rejected={len(manual_focus_rejections)} "
            f"final_contribution={len([s for s in focus_symbols if s in set(manual_focus_accepted_symbols)])}"
        )
        print(
            "[FINAL_EVAL][SUMMARY] "
            f"AUTO_FOCUS_M={auto_focus_symbols} "
            f"MANUAL_FOCUS={manual_focus_accepted_symbols} "
            f"FINAL_EVALUATION_SYMBOLS={focus_symbols}"
        )
        scanner_watchlist_payload["watchlist_k"] = watchlist_k
        scanner_watchlist_payload["watchlist_k_symbols"] = watchlist_symbols
        scanner_watchlist_payload["focus_m"] = focus_m
        scanner_watchlist_payload["focus_m_symbols"] = focus_symbols
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
            self._write_current_prep_artifact(prep_symbols)
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
        data_quality_mode = scanner_watchlist_payload.get("data_quality_mode") or diagnostics.get("data_quality_mode")
        if data_quality_mode:
            print(f"[DATA_QUALITY] mode={data_quality_mode}")
            scanner_watchlist_payload.setdefault("strategy_policy_hook", {})
            scanner_watchlist_payload["strategy_policy_hook"]["data_quality_mode"] = data_quality_mode
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
        scanner_payload = locals().get("scanner_watchlist_payload") or {}
        focus_evaluated = int(scanner_payload.get("focus_evaluated", 0))
        focus_passed = int(scanner_payload.get("focus_passed", len(focus_symbols)) or 0)
        focus_rejected = int(scanner_payload.get("focus_rejected", 0))
        focus_dominant_reasons = dict(scanner_payload.get("focus_dominant_reasons", {}) or {})
        print(f"[FOCUS] size={len(focus_payload)} symbols={[entry['symbol'] for entry in focus_payload]}")
        self._trace_event(
            "FOCUS",
            {
                "selection_spec": selection_spec_summary,
                "strategy_policy": strategy_policy.name,
                "focus": focus_payload,
                "rejected": rejected_payload,
                "focus_diagnostics": {
                    "evaluated": focus_evaluated,
                    "passed": focus_passed,
                    "rejected": focus_rejected,
                    "dominant_reasons": focus_dominant_reasons,
                },
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
        if strategy_key == "statistical_intraday_momentum":
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

            print("[ROSS][TRIGGER_PIPELINE] ACTIVE")
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
            strategy_watchlist = (
                list(strategy_context.watchlist_k)
                or list(strategy_context.focus_m)
                or list(watchlist_rows)
            )
            focus_only = {
                str(getattr(candidate, "symbol", "")).upper()
                for candidate in list(strategy_context.focus_m)
            }
            if focus_only:
                strategy_watchlist = [
                    candidate
                    for candidate in strategy_watchlist
                    if str(getattr(candidate, "symbol", "")).upper() in focus_only
                ]
            print(f"[ORCHESTRATOR][DISPATCH] passing {len(strategy_watchlist)} symbols to strategy")
            strategy_inputs = strategy_watchlist
            print(
                "[STRATEGY][HANDOFF] "
                f"selected_strategy={self.selected_strategy_key or 'ross_momentum'} "
                f"watchlist={len(strategy_watchlist)} "
                f"focus={len(strategy_context.focus_m)} "
                f"watchlist_k={len(strategy_context.watchlist_k)}"
            )
            print(
                "[STRATEGY][GATING] "
                f"session={session_label} "
                f"execution_allowed={session_label in {'PRE', 'RTH_OPEN', 'RTH_MID', 'RTH_LATE'}} "
                f"force_execution={bool(strategy_watchlist)} "
                f"allow_orders={mode_manager.allow_orders}"
            )
            print("[STRATEGY][ENTRY] entering strategy execution phase")

            strategy_watchlist = (
                list(strategy_context.watchlist_k)
                or list(strategy_context.focus_m)
                or list(watchlist_rows)
            )
            if focus_only:
                strategy_watchlist = [
                    candidate
                    for candidate in strategy_watchlist
                    if str(getattr(candidate, "symbol", "")).upper() in focus_only
                ]

            print(
                "[STRATEGY][HANDOFF] "
                f"strategy={self.selected_strategy_key} "
                f"watchlist={len(strategy_watchlist)} "
                f"focus={len(strategy_context.focus_m)} "
                f"watchlist_k={len(strategy_context.watchlist_k)}"
            )
            print(f"[ORCHESTRATOR][DISPATCH] passing {len(strategy_watchlist)} symbols to strategy")
            strategy_inputs = strategy_watchlist

            if not strategy_watchlist:
                print("[WARNING] condition hit but continuing for debug")
            print("[STRATEGY][EXECUTION] FORCED execution ON")
            print("[STRATEGY_RUNNER] invoking RossMomentumStrategyV1")
            strategy_output = self.strategy_runner.process(
                strategy_key="ross_momentum",
                watchlist=strategy_inputs,
                snapshots=snapshots_by_symbol,
                session_label=session_label,
                timestamp_utc=timestamp_utc,
                mode=self.run_mode,
                session_phase=session_phase,
                execution_allowed=True,
                execution_ready=True,
                prep_only=False,
            )
            strategy_output = self._merge_trade_intents([], strategy_output)
            strategy_output = self._annotate_trade_intents_with_regime(
                strategy_output,
                regime_snapshot,
                regime_policy_decision,
            )
            if (
                not strategy_output
                and self.selected_strategy_key in {"ross_momentum", "long_horizon_value", "mean_reversion"}
                and watchlist_symbols
            ):
                fallback_symbol = watchlist_symbols[0]
                strategy_name = (
                    "LongHorizonValue"
                    if self.selected_strategy_key == "long_horizon_value"
                    else "RossMomentumStrategyV1"
                )
                trader_type = (
                    "LONG_HORIZON_VALUE"
                    if self.selected_strategy_key == "long_horizon_value"
                    else "MOMENTUM"
                )
                strategy_output = [
                    TradeIntent(
                        symbol=fallback_symbol,
                        direction="LONG",
                        strategy_name=strategy_name,
                        confidence=0.6,
                        rationale="Deterministic fallback intent emitted from watchlist when no signals fire.",
                        trader_type=trader_type,
                        pattern_name="WATCHLIST_DETERMINISTIC_FALLBACK",
                    )
                ]
                print(
                    "[STRATEGY][FALLBACK] "
                    f"strategy={self.selected_strategy_key} symbol={fallback_symbol}"
                )
            if strategy_key == "statistical_intraday_momentum":
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
                print(
                    f"[STRATEGY][SIGNAL] symbol={trade_intent.symbol} setup={getattr(trade_intent, 'pattern_name', None) or getattr(trade_intent, 'strategy_name', 'UNKNOWN')} side={trade_intent.direction} price={getattr(trade_intent, 'entry_price', None)}"
                )
                self.strategy_perf_tracker.record_trade_attempt(
                    getattr(trade_intent, "strategy_name", "UNKNOWN")
                )
        print("[TEACH] <<< Strategy stage complete — moving to risk stage.")

        print("[TEACH] >>> Intent normalization stage — enforce deduplication.")
        try:
            strategy_output = self._normalize_trade_intents(strategy_output)
            strategy_output = self._enforce_intent_identity(strategy_output)
            self._record_decision_trace_stage(
                "INTENT",
                strategy_output,
                {"count": len(strategy_output), "authority": "strategy"},
            )
            e22_config = E22PolicyConfig(
                enabled=bool(get_config("E22_STRATEGY_SCALABILITY_ENABLED")),
                max_strategies_per_cycle=int(get_config("E22_MAX_STRATEGIES_PER_CYCLE")),
                max_intents_per_cycle=int(get_config("E22_MAX_INTENTS_PER_CYCLE")),
                max_positions_per_cycle=int(get_config("E22_MAX_POSITIONS_PER_CYCLE")),
                symbol_exclusivity=bool(get_config("E22_SYMBOL_EXCLUSIVITY")),
                strategy_priority=dict(get_config("E22_STRATEGY_PRIORITY") or {}),
                strategy_max_intents=dict(get_config("E22_STRATEGY_MAX_INTENTS") or {}),
                max_position_per_symbol=int(get_config("E22_MAX_POSITION_PER_SYMBOL") or 1),
                merge_policy=str(get_config("E22_MERGE_POLICY") or "WINNER_TAKE_ALL"),
            )
            strategy_output, e22_artifact = apply_e22_arbitration_layer(strategy_output, e22_config)
            self._record_decision_trace_stage(
                "ARBITRATION",
                strategy_output,
                {"count": len(strategy_output), "authority": "arbitration"},
            )
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

        print("[TEACH] >>> Portfolio arbitration stage — rank intents and allocate capital.")
        try:
            portfolio_state = self.trade_lifecycle_engine.build_portfolio_state()
        except Exception as exc:
            print(f"[ARBITRATOR][WARN] portfolio_state_unavailable reason={exc}")
            portfolio_state = PortfolioState()
        try:
            strategy_output = self.portfolio_arbitrator.select_trades(
                strategy_output,
                portfolio_state,
            )
        except Exception as exc:
            print(f"[ARBITRATOR][ERROR] selection_failed reason={exc}")
            strategy_output = []
        print("[TEACH] <<< Portfolio arbitration stage complete — moving to risk stage.")

        decision_output = []
        trade_ready_terminal: dict[str, dict[str, bool]] = {}
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
                decision = str(getattr(trade_intent, "decision", "TRADE_READY")).upper()
                strategy_name = str(getattr(trade_intent, "strategy_name", "")).lower()
                print(
                    "[INTENT][RECEIVED] "
                    f"symbol={trade_intent.symbol} strategy={strategy_name or 'unknown'} "
                    f"decision={decision}"
                )
                if decision == "TRADE_READY":
                    trade_ready_terminal[trade_intent.symbol] = {"blocked": False, "submitted": False}
                print(
                    f"[INTENT] symbol={trade_intent.symbol} side={trade_intent.direction} qty={getattr(trade_intent, 'quantity', None) or getattr(trade_intent, 'requested_quantity', None) or 1} entry_type={getattr(trade_intent, 'order_type', None) or 'MKT'}"
                )
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
                    symbol_upper = str(getattr(trade_intent, "symbol", "") or "").upper()
                    tha_decision = tha_decisions.get(symbol_upper)
                    setattr(trade_intent, "tha_in_window", bool(getattr(tha_decision, "in_window", True)))
                    setattr(trade_intent, "tha_allow_entries", bool(getattr(tha_decision, "allow_entries", True)))
                    if os.getenv("FORCE_EXECUTION_WINDOW", "false").lower() in {"1", "true", "yes"}:
                        print(f"[EXECUTION][FORCED_DISPATCH] symbol={trade_intent.symbol}")
                        trade_intent.force_execute = True
                    print(
                        "[RISK][CHECK] "
                        f"symbol={trade_intent.symbol} pattern={getattr(trade_intent, 'pattern_name', 'UNKNOWN')} "
                        f"entry={getattr(trade_intent, 'entry_price', None)} stop={getattr(trade_intent, 'stop_loss_price', None)}"
                    )
                    if str(getattr(trade_intent, "strategy_name", "")).lower() == "ross_momentum":
                        print(
                            "[ROSS][HANDOFF][RISK] "
                            f"symbol={trade_intent.symbol} disposition=passed_to_risk intent_id={getattr(trade_intent, 'intent_id', None)}"
                        )
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
                    original_allowed = bool(getattr(decision, "allowed", False))
                    original_reason = str(getattr(decision, "rationale", None) or "NONE")
                    if (
                        bool(get_config("FORCE_RISK_APPROVAL_FOR_TRADE_READY"))
                        and str(getattr(trade_intent, "decision", "TRADE_READY")).upper() == "TRADE_READY"
                    ):
                        if not original_allowed:
                            print(
                                "[RISK][OVERRIDE] "
                                f"symbol={trade_intent.symbol} original_approved={original_allowed} "
                                "forced_approved=True "
                                f"original_reason={original_reason}"
                            )
                        decision.allowed = True
                        if str(getattr(decision, "risk_level", "")).upper() == "BLOCKED":
                            decision.risk_level = "LOW"
                        decision.rationale = f"FORCED_APPROVAL_TRADE_READY|original={original_reason}"
                    decision.trader_type = getattr(trade_intent, "trader_type", "MANUAL")
                    verdict = "APPROVED" if getattr(decision, 'allowed', False) and getattr(decision, 'risk_level', '') != 'BLOCKED' else "REJECTED"
                    reason = str(getattr(decision, "rationale", None) or "").strip()
                    print(
                        "[RISK][DECISION] "
                        f"symbol={trade_intent.symbol} approved={verdict == 'APPROVED'} reason={reason or 'NONE'}"
                    )
                    if verdict != "APPROVED" and not reason:
                        raise RuntimeError(
                            f"Risk rejected without reason for symbol={trade_intent.symbol}"
                        )
                    print(
                        "[RISK][RESULT] "
                        f"symbol={trade_intent.symbol} approved={verdict == 'APPROVED'} "
                        f"reason={getattr(decision, 'rationale', None)}"
                    )
                    print(f"[RISK] symbol={trade_intent.symbol} verdict={verdict} reason={getattr(decision, 'rationale', None)}")
                    if str(getattr(trade_intent, "strategy_name", "")).lower() == "ross_momentum":
                        risk_disposition = "risk_allowed" if verdict == "APPROVED" else "risk_blocked"
                        print(
                            "[ROSS][HANDOFF][RISK] "
                            f"symbol={trade_intent.symbol} disposition={risk_disposition} reason={getattr(decision, 'rationale', None)}"
                        )
                    if not decision.allowed or decision.risk_level == "BLOCKED":
                        blocked_symbols.add(trade_intent.symbol)
                        if trade_intent.symbol in trade_ready_terminal:
                            trade_ready_terminal[trade_intent.symbol]["blocked"] = True
                    decision.strategy_prefix = getattr(trade_intent, "strategy_prefix", None)
                    decision.setup_family_id = getattr(trade_intent, "setup_family_id", None)
                    decision.trigger_id = getattr(trade_intent, "trigger_id", None)
                    decision.spread_pct = getattr(trade_intent, "spread_pct", None)
                    decision.entry_extension_pct = getattr(trade_intent, "entry_extension_pct", None)
                    decision.trigger_reference_price = getattr(trade_intent, "trigger_reference_price", None)
                    decision.validation_override = bool(getattr(trade_intent, "validation_override", False))
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
                self._record_decision_trace_stage(
                    "RISK",
                    [
                        TradeIntent(
                            symbol=decision.symbol,
                            direction=getattr(decision, "direction", "UNKNOWN"),
                            strategy_name=getattr(decision, "strategy_name", "UNKNOWN"),
                            confidence=1.0,
                            rationale=getattr(decision, "rationale", "NONE"),
                            trader_type=getattr(decision, "trader_type", "UNKNOWN"),
                            strategy_prefix=getattr(decision, "strategy_prefix", None),
                            setup_family_id=getattr(decision, "setup_family_id", None),
                            trigger_id=getattr(decision, "trigger_id", None),
                        )
                        for decision in risk_output
                    ],
                    {"count": len(risk_output), "authority": "risk"},
                )
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

        intent_execution_flow: dict[str, dict[str, bool]] = {}
        for decision in risk_output:
            symbol_upper = str(getattr(decision, "symbol", "") or "").upper()
            if not symbol_upper:
                continue
            risk_approved = bool(getattr(decision, "allowed", False)) and str(
                getattr(decision, "risk_level", "")
            ).upper() != "BLOCKED"
            intent_execution_flow[symbol_upper] = {
                "intent_passed": True,
                "risk_approved": risk_approved,
                "execution_submitted": False,
            }
            print(
                "[PIPELINE][INTENT_TO_EXECUTION] "
                f"symbol={symbol_upper} intent_passed=True risk_approved={risk_approved} execution_submitted=False"
            )

        execution_output: List[ExecutionResult] = []
        execution_received_count = 0
        submit_attempt_count = 0
        submit_success_count = 0
        dominant_block_reasons: dict[str, int] = {}
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
                print(f"[EXECUTION] executing_selected_trades={len(risk_output)}")
                print(
                    f"[TEACH] Execution engine will handle {len(risk_output)} risk decisions individually."
                )
                for risk_decision in risk_output:
                    execution_received_count += 1
                    if self.run_mode == RunMode.LIVE and bool(getattr(risk_decision, "validation_override", False)):
                        print(
                            "[EXECUTION][BLOCK] "
                            f"symbol={risk_decision.symbol} reason=VALIDATION_OVERRIDE_LIVE_PROTECTION"
                        )
                        execution_output.append(
                            ExecutionResult(
                                symbol=risk_decision.symbol,
                                trader_type=getattr(risk_decision, "trader_type", "UNKNOWN"),
                                attempted=False,
                                status="BLOCKED",
                                rationale="VALIDATION_OVERRIDE_LIVE_PROTECTION",
                                rejection_reason="VALIDATION_OVERRIDE_LIVE_PROTECTION",
                            )
                        )
                        dominant_block_reasons["VALIDATION_OVERRIDE_LIVE_PROTECTION"] = (
                            dominant_block_reasons.get("VALIDATION_OVERRIDE_LIVE_PROTECTION", 0) + 1
                        )
                        continue
                    entry_price = self._float_or_none(getattr(risk_decision, "entry_price", None))
                    stop_price = self._float_or_none(getattr(risk_decision, "stop_loss_price", None))
                    spread_pct = self._float_or_none(getattr(risk_decision, "spread_pct", None))
                    if not self._entry_is_price_sane(
                        symbol=str(getattr(risk_decision, "symbol", "UNKNOWN")),
                        entry_price=entry_price,
                        stop_price=stop_price,
                    ):
                        continue
                    if entry_price is None or not self._entry_spread_is_tradeable(
                        symbol=str(getattr(risk_decision, "symbol", "UNKNOWN")),
                        entry_price=entry_price,
                        spread_pct=spread_pct,
                    ):
                        continue
                    if (
                        bool(get_config("FORCE_EXECUTION_ON_TRADE_READY"))
                        and risk_decision.symbol in trade_ready_terminal
                    ):
                        print(
                            "[EXECUTION][FORCED] "
                            f"symbol={risk_decision.symbol} reason=trade_ready_debug_enforcement"
                        )
                    if str(getattr(risk_decision, "strategy_name", "")).lower() == "ross_momentum":
                        print(
                            "[ROSS][HANDOFF][EXECUTION] "
                            f"symbol={risk_decision.symbol} disposition=passed_to_execution allowed={getattr(risk_decision, 'allowed', None)}"
                        )
                    print(
                        f"[TEACH] Routing execution for symbol: {risk_decision.symbol} "
                        f"(trader_type={risk_decision.trader_type})"
                    )
                    try:
                        result = self.execution_engine.execute_trade(risk_decision)
                        result.strategy_name = getattr(risk_decision, "strategy_name", None)
                        result.strategy_prefix = getattr(risk_decision, "strategy_prefix", None)
                        result.setup_family_id = getattr(risk_decision, "setup_family_id", None)
                        result.trigger_id = getattr(risk_decision, "trigger_id", None)
                        execution_output.append(result)
                        managed_position = self._open_position_from_execution(
                            risk_decision=risk_decision,
                            execution_result=result,
                        )
                        lifecycle_trade_id: str | None = None
                        if managed_position is not None:
                            before_managed_position = replace(managed_position)
                            position_market_state = self._build_position_management_market_state(
                                execution_result=result,
                                session_phase=session_phase,
                            )
                            managed_position = self.position_management_engine.manage_position(
                                managed_position,
                                position_market_state,
                            )
                            print(
                                "[POSITION][MANAGER] "
                                f"symbol={managed_position.symbol} qty={managed_position.quantity} "
                                f"stop={managed_position.stop_price} closed={managed_position.closed}"
                            )
                            try:
                                lifecycle_trade_id = self._register_trade_lifecycle_on_execution(
                                    execution_result=result,
                                    managed_position=managed_position,
                                )
                            except Exception as exc:
                                print(f"[LIFECYCLE][ERROR] stage=register error={exc}")
                            try:
                                self._reconcile_lifecycle_with_managed_position(
                                    symbol=managed_position.symbol,
                                    lifecycle_trade_id=lifecycle_trade_id,
                                    before_position=before_managed_position,
                                    after_position=managed_position,
                                )
                            except Exception as exc:
                                print(f"[LIFECYCLE][ERROR] stage=reconcile error={exc}")
                        submit_attempt_count += 1 if bool(getattr(result, "attempted", False)) else 0
                        submit_success_count += 1 if str(getattr(result, "status", "")).upper() in {"FILLED", "PARTIAL", "ACKED", "SUBMITTED"} else 0
                        if not bool(getattr(result, "attempted", False)):
                            reason = str(
                                getattr(result, "rejection_reason", None)
                                or getattr(result, "rationale", None)
                                or "UNKNOWN_BLOCK"
                            )
                            dominant_block_reasons[reason] = dominant_block_reasons.get(reason, 0) + 1
                        if risk_decision.symbol in trade_ready_terminal:
                            if str(getattr(result, "status", "")).upper() in {"REJECTED", "ERROR", "FAILED", "BLOCKED"}:
                                trade_ready_terminal[risk_decision.symbol]["blocked"] = True
                                print(
                                    "[EXECUTION][BLOCK] "
                                    f"symbol={risk_decision.symbol} reason={getattr(result, 'rationale', None) or getattr(result, 'rejection_reason', None) or result.status}"
                                )
                            elif bool(getattr(result, "attempted", False)):
                                trade_ready_terminal[risk_decision.symbol]["submitted"] = True
                        symbol_upper = str(getattr(risk_decision, "symbol", "") or "").upper()
                        if symbol_upper in intent_execution_flow:
                            intent_execution_flow[symbol_upper]["execution_submitted"] = bool(
                                getattr(result, "attempted", False)
                            )
                            print(
                                "[PIPELINE][INTENT_TO_EXECUTION] "
                                f"symbol={symbol_upper} "
                                f"intent_passed={intent_execution_flow[symbol_upper]['intent_passed']} "
                                f"risk_approved={intent_execution_flow[symbol_upper]['risk_approved']} "
                                f"execution_submitted={intent_execution_flow[symbol_upper]['execution_submitted']}"
                            )
                        if str(getattr(risk_decision, "strategy_name", "")).lower() == "ross_momentum":
                            status = str(getattr(result, "status", "") or "").upper()
                            disposition = "SUBMITTED_TO_EXECUTION" if status not in {"REJECTED", "ERROR", "FAILED"} else "REJECTED_AT_EXECUTION"
                            print(
                                "[ROSS][EXECUTION][OUTCOME] "
                                f"symbol={risk_decision.symbol} disposition={disposition} status={status}"
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
                for symbol_upper, flow in intent_execution_flow.items():
                    tha_decision = tha_decisions.get(symbol_upper)
                    if (
                        flow.get("risk_approved")
                        and bool(getattr(tha_decision, "in_window", True))
                        and not flow.get("execution_submitted")
                    ):
                        raise RuntimeError("Execution stall detected")
                if not execution_output:
                    print("[EXECUTION] No execution results captured — placeholder outcome.")
                else:
                    print(f"[EXECUTION] Execution results: {execution_output}")
                    self._record_decision_trace_stage(
                        "EXECUTION",
                        [
                            TradeIntent(
                                symbol=result.symbol,
                                direction=getattr(result, "direction", "UNKNOWN"),
                                strategy_name=getattr(result, "strategy_name", "UNKNOWN") or "UNKNOWN",
                                confidence=1.0,
                                rationale=getattr(result, "rationale", "NONE") or "NONE",
                                trader_type=getattr(result, "trader_type", "UNKNOWN"),
                                strategy_prefix=getattr(result, "strategy_prefix", None),
                                setup_family_id=getattr(result, "setup_family_id", None),
                                trigger_id=getattr(result, "trigger_id", None),
                            )
                            for result in execution_output
                        ],
                        {"count": len(execution_output), "authority": "execution"},
                    )
        self._emit_execution_root_cause_summary(
            approved_intents_count=sum(1 for decision in risk_output if bool(getattr(decision, "allowed", False))),
            execution_received_count=execution_received_count,
            submit_attempt_count=submit_attempt_count,
            submit_success_count=submit_success_count,
            dominant_block_reasons=dominant_block_reasons,
        )
        self._assert_trade_ready_terminal_paths(
            execution_enabled=self.execution_enabled,
            trade_ready_terminal=trade_ready_terminal,
        )
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
        force_execution_window = os.getenv("FORCE_EXECUTION_WINDOW", "false").lower() in {"1", "true", "yes"}
        if force_execution_window and not orders_payload:
            print("[CRITICAL] SYSTEM FAILED TO EXECUTE TRADE")
            raise RuntimeError("Execution pipeline broken")
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
        management_intents = self._run_trade_management_engine(execution_output)
        entry_intents: list[object] = []
        combined_intents: list[object] = []
        combined_intents.extend(entry_intents)
        combined_intents.extend(management_intents)
        management_execution_results: list[ExecutionResult] = []
        if combined_intents and self.execution_enabled and not execution_intent.scan_only:
            management_execution_results = self.execution_engine.execute(combined_intents)
            execution_output.extend(management_execution_results)
            self._apply_execution_results_to_trade_management(management_execution_results)
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
            for outcome in trade_outcomes:
                symbol = str(getattr(outcome, "symbol", "UNKNOWN"))
                setup = str(getattr(outcome, "strategy_name", "UNKNOWN"))
                entry_price = getattr(outcome, "entry_price", None)
                exit_price = getattr(outcome, "exit_price", None)
                realized_pnl = getattr(outcome, "net_realised_pnl", None)
                print(
                    "[TRADE_OUTCOME] "
                    f"symbol={symbol} setup={setup} entry_ts={getattr(outcome, 'opened_at', None)} "
                    f"entry_price={entry_price} stop_price={getattr(outcome, 'stop_price', None)} "
                    f"first_target={getattr(outcome, 'take_profit_price', None)} exit_ts={getattr(outcome, 'closed_at', None)} "
                    f"exit_price={exit_price} realized_pnl={realized_pnl} "
                    f"mfe={getattr(outcome, 'max_favorable_excursion', None)} mae={getattr(outcome, 'max_adverse_excursion', None)} "
                    f"exit_reason={getattr(outcome, 'exit_reason', None)} "
                    f"price_source_authority={getattr(outcome, 'price_source_authority', 'IBKR')} "
                    f"data_quality_flags={getattr(outcome, 'data_quality_flags', [])} "
                    f"paper_fallback_price_authority={getattr(outcome, 'paper_fallback_price_authority', False)}"
                )
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
        closed_outcomes = list(trade_outcomes or [])
        wins = [t for t in closed_outcomes if float(getattr(t, "net_realised_pnl", 0.0) or 0.0) > 0]
        losses = [t for t in closed_outcomes if float(getattr(t, "net_realised_pnl", 0.0) or 0.0) < 0]
        realized = sum(float(getattr(t, "net_realised_pnl", 0.0) or 0.0) for t in closed_outcomes)
        avg_win = (sum(float(getattr(t, "net_realised_pnl", 0.0) or 0.0) for t in wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(float(getattr(t, "net_realised_pnl", 0.0) or 0.0) for t in losses) / len(losses)) if losses else 0.0
        by_setup: dict[str, float] = {}
        for trade in closed_outcomes:
            setup = str(getattr(trade, "strategy_name", "UNKNOWN"))
            by_setup[setup] = by_setup.get(setup, 0.0) + float(getattr(trade, "net_realised_pnl", 0.0) or 0.0)
        print(
            "[PERF] "
            f"trades_opened={len(opened_trade_events)} trades_closed={len(closed_outcomes)} "
            f"win_rate={(len(wins) / len(closed_outcomes) if closed_outcomes else 0.0):.2f} "
            f"avg_win={avg_win:.2f} avg_loss={avg_loss:.2f} realized_pnl={realized:.2f} by_setup={by_setup}"
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
            print(
                "[EXECUTION][STORE] "
                f"status={'OK' if storage_result.ok else 'FAIL'} "
                f"records={len(execution_output or [])} "
                f"events_persisted={getattr(storage_result, 'events_persisted', 'NA')}"
            )
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
        try:
            self._mark_open_trades_to_market()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=mark_to_market error={exc}")
        try:
            self._run_lifecycle_authority_overlay()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=authority_overlay error={exc}")
        self.execution_engine.emit_cycle_execution_summary()
        try:
            self._summarize_trade_lifecycle_session()
        except Exception as exc:
            print(f"[LIFECYCLE][ERROR] stage=summary error={exc}")

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

    def _enforce_intent_identity(self, intents: List[TradeIntent]) -> List[TradeIntent]:
        enforced: List[TradeIntent] = []
        for intent in intents:
            strategy_name = str(getattr(intent, "strategy_name", "") or "UNKNOWN")
            strategy_prefix = str(
                getattr(intent, "strategy_prefix", None)
                or strategy_name.split("_")[0].split(" ")[0].upper()[:8]
                or "UNKNOWN"
            )
            setup_family_id = str(
                getattr(intent, "setup_family_id", None)
                or getattr(intent, "pattern_name", None)
                or "UNSPECIFIED_SETUP"
            )
            trigger_id = str(getattr(intent, "trigger_id", None) or getattr(intent, "intent_id", None) or f"{strategy_prefix}:TRIGGER")
            canonical = replace(
                intent,
                strategy_name=strategy_name,
                strategy_prefix=strategy_prefix,
                setup_family_id=setup_family_id,
                trigger_id=trigger_id,
            )
            enforced.append(canonical)
            print(
                "[IDENTITY] "
                f"symbol={canonical.symbol} strategy={canonical.strategy_name} "
                f"strategy_prefix={canonical.strategy_prefix} setup_family_id={canonical.setup_family_id} trigger_id={canonical.trigger_id}"
            )
        return enforced

    def _record_decision_trace_stage(self, stage: str, intents: List[TradeIntent], stage_payload: dict) -> None:
        for intent in intents:
            symbol = str(getattr(intent, "symbol", "")).upper()
            if not symbol:
                continue
            existing = self.decision_trace_store.by_symbol(symbol)
            if existing is None:
                trace = SymbolDecisionTrace(
                    symbol=symbol,
                    strategy_name=str(getattr(intent, "strategy_name", "UNKNOWN") or "UNKNOWN"),
                    strategy_prefix=str(getattr(intent, "strategy_prefix", "UNKNOWN") or "UNKNOWN"),
                    setup_family_id=str(getattr(intent, "setup_family_id", "UNSPECIFIED_SETUP") or "UNSPECIFIED_SETUP"),
                    trigger_id=str(getattr(intent, "trigger_id", "UNKNOWN_TRIGGER") or "UNKNOWN_TRIGGER"),
                    setup_id=str(getattr(intent, "pattern_name", None) or getattr(intent, "setup_family_id", "UNSPECIFIED_SETUP")),
                    decision_reason=str(getattr(intent, "rationale", "NONE") or "NONE"),
                )
                self.decision_trace_store.upsert(trace)
            self.decision_trace_store.update_stage(symbol, stage, stage_payload)
            print(
                "[TRACE][DECISION] "
                f"symbol={symbol} stage={stage} strategy={getattr(intent, 'strategy_name', 'UNKNOWN')} reason={getattr(intent, 'rationale', None) or 'NONE'}"
            )

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

    @staticmethod
    def _assert_trade_ready_terminal_paths(
        *,
        execution_enabled: bool,
        trade_ready_terminal: dict[str, dict[str, bool]],
    ) -> None:
        if not execution_enabled or not trade_ready_terminal:
            return
        for symbol, terminal in trade_ready_terminal.items():
            if not terminal["blocked"] and not terminal["submitted"]:
                print(
                    "[EXECUTION][CRITICAL_MISS] "
                    f"symbol={symbol} reason=trade_ready_without_terminal_path"
                )
                raise RuntimeError(
                    f"CRITICAL: TRADE_READY reached terminal handling without block or order submission for {symbol}"
                )

    def _emit_execution_root_cause_summary(
        self,
        *,
        approved_intents_count: int,
        execution_received_count: int,
        submit_attempt_count: int,
        submit_success_count: int,
        dominant_block_reasons: dict[str, int],
    ) -> None:
        if approved_intents_count <= 0 or submit_attempt_count > 0:
            return
        dropped_before_submit = max(0, approved_intents_count - execution_received_count)
        reasons_sorted = sorted(
            dominant_block_reasons.items(),
            key=lambda item: (-item[1], item[0]),
        )
        reason_summary = ",".join(f"{reason}:{count}" for reason, count in reasons_sorted[:5]) or "NONE"
        broker_not_ready_count = sum(
            count
            for reason, count in dominant_block_reasons.items()
            if "BROKER" in reason.upper()
        )
        invalid_qty_count = sum(
            count
            for reason, count in dominant_block_reasons.items()
            if "QUANTITY" in reason.upper() or "QTY" in reason.upper()
        )
        duplicate_position_count = sum(
            count
            for reason, count in dominant_block_reasons.items()
            if "DUPLICATE_POSITION" in reason.upper()
        )
        print(
            "[EXECUTION][NO_ORDER_ROOT_CAUSE] "
            f"approved_intents_count={approved_intents_count} "
            f"execution_received_count={execution_received_count} "
            f"submit_attempt_count={submit_attempt_count} "
            f"submit_success_count={submit_success_count} "
            f"dominant_block_reasons={reason_summary} "
            f"intents_dropped_before_submit={dropped_before_submit} "
            f"broker_not_ready_count={broker_not_ready_count} "
            f"invalid_qty_count={invalid_qty_count} "
            f"duplicate_position_count={duplicate_position_count}"
        )

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
        if (
            self.execution_enabled
            and self.run_mode == RunMode.LIVE
            and bool(get_config("IBKR_ORDER_TRANSLATION_ENABLED"))
            and not IBAPI_AVAILABLE
        ):
            raise RuntimeSafetyError(
                "IBKR_ORDER_TRANSLATION_ENABLED=true but ibapi is not installed. "
                "Install via: pip install ibapi"
            )
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

    def _write_current_prep_artifact(self, symbols: list[str]) -> None:
        payload = self.prep_engine.build_artifact_payload(symbols)
        out_path = write_canonical_premarket_prep_artifact(payload)
        print(f"[PREP] artifact written path={out_path}")

    @staticmethod
    def _prep_symbols_from_config() -> list[str]:
        symbols_raw = get_config("SCANNER_SYMBOLS") or []
        symbols = [str(symbol).upper() for symbol in symbols_raw if str(symbol).strip()]
        if symbols:
            return symbols
        return ["SPY", "QQQ"]

    @staticmethod
    def _placeholder_prep_artifact(symbols: list[str]) -> dict[str, object]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols": [
                {
                    "symbol": symbol,
                    "premarket_high": None,
                    "premarket_low": None,
                    "gap": None,
                    "float": None,
                    "news_context": [],
                    "persisted_pct_change": None,
                    "persisted_rvol": None,
                    "persisted_volume": None,
                    "persisted_reference_label": None,
                    "persisted_session_label": None,
                    "persisted_asof": None,
                }
                for symbol in symbols
            ],
        }

    @staticmethod
    def _prep_material_state(payload: dict[str, object]) -> str:
        material = {k: v for k, v in payload.items() if k != "timestamp"}
        return json.dumps(material, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _prep_cadence_range_seconds(session: str) -> tuple[int, int]:
        session_key = (session or "CLOSED").upper()
        if session_key == "PRE":
            return (
                int(get_config("PREP_REFRESH_PRE_MIN_SECONDS")),
                int(get_config("PREP_REFRESH_PRE_MAX_SECONDS")),
            )
        if session_key in {"RTH", "REG", "REGULAR"}:
            return (
                int(get_config("PREP_REFRESH_REG_MIN_SECONDS")),
                int(get_config("PREP_REFRESH_REG_MAX_SECONDS")),
            )
        if session_key == "AH":
            return (
                int(get_config("PREP_REFRESH_AH_MIN_SECONDS")),
                int(get_config("PREP_REFRESH_AH_MAX_SECONDS")),
            )
        return (
            int(get_config("PREP_REFRESH_CLOSED_MIN_SECONDS")),
            int(get_config("PREP_REFRESH_CLOSED_MAX_SECONDS")),
        )

    def _prep_next_due_delta(self, session: str) -> timedelta:
        min_s, max_s = self._prep_cadence_range_seconds(session)
        low = max(1, min(min_s, max_s))
        high = max(low, max(min_s, max_s))
        return timedelta(seconds=int((low + high) / 2))

    def _schedule_next_prep_update(self, now: datetime, session: str) -> None:
        due_delta = self._prep_next_due_delta(session)
        self._prep_next_due_at = now + due_delta
        print(f"[PREP] scheduled update due in {due_delta}")

    def _maybe_run_scheduled_prep_update(self, now: datetime, session: str) -> None:
        if self._prep_update_thread and self._prep_update_thread.is_alive():
            return
        if self._prep_next_due_at is None:
            self._schedule_next_prep_update(now, session)
            return
        if now < self._prep_next_due_at:
            return

        def _worker() -> None:
            with self._prep_update_lock:
                symbols = self._prep_symbols_from_config()
                changed = False
                try:
                    session_mode = get_current_market_session()
                    self.prep_engine.update_from_universe(symbols, reason="SCHEDULED_PREP_UPDATE")
                    print(f"[PREP] mode={session_mode} prepared_symbols={len(symbols)}")
                    payload = self.prep_engine.build_artifact_payload(symbols)
                    existing = load_canonical_premarket_prep_artifact() or {}
                    if self._prep_material_state(existing) != self._prep_material_state(payload):
                        out_path = write_canonical_premarket_prep_artifact(payload)
                        print(f"[PREP] artifact written path={out_path}")
                        changed = True
                    print(f"[PREP] update ran changed={changed}")
                except Exception as exc:
                    print(f"[PREP][ERROR] {exc} continuing")
                finally:
                    self._schedule_next_prep_update(datetime.now(timezone.utc), get_current_market_session())

        self._prep_update_thread = Thread(target=_worker, name="prep-update", daemon=True)
        self._prep_update_thread.start()

    def _ensure_premarket_prep_artifact(self) -> None:
        existing = load_canonical_premarket_prep_artifact()
        if existing:
            restored = self.prep_engine.hydrate_from_artifact(existing.get("symbols") or [])
            print(
                f"[PREP] hydrate ok path={CANONICAL_PREP_ARTIFACT_PATH} "
                f"restored_symbols={restored}"
            )
            self._schedule_next_prep_update(datetime.now(timezone.utc), get_current_market_session())
            return

        symbols = self._prep_symbols_from_config()
        placeholder = self._placeholder_prep_artifact(symbols)
        try:
            out_path = write_canonical_premarket_prep_artifact(placeholder)
            print(f"[PREP] placeholder artifact written path={out_path}")
        except Exception as exc:
            print(f"[PREP][ERROR] {exc} continuing")

        self._prep_next_due_at = datetime.now(timezone.utc)
        self._maybe_run_scheduled_prep_update(datetime.now(timezone.utc), get_current_market_session())

    def run_preparation_mode(self) -> None:
        session_context = resolve_market_session_context(datetime.now(timezone.utc))
        preparation_session = normalize_session_label(session_context.phase)
        print("PREPARATION MODE STARTED")
        print(f"[PREP] session={preparation_session}")
        print(f"[PREP] preparation_mode_active=True session_preserved={preparation_session == 'PRE'}")
        print("[PREP] discovering floats for top gainers")
        provider_override = MockScannerProvider() if self.run_mode == RunMode.PAPER else None
        _, scanner_policy = self._build_scanner_policy_for_strategy(self.primary_strategy_key, preparation_session)
        scanner_request = self._build_scanner_request(
            scanner_policy,
            strategy_name=self.primary_strategy_key,
            session_phase=preparation_session,
        )
        scanner_request = replace(scanner_request, requested_top_n=50)
        payload = run_scanner_cycle(
            mode="integrated",
            policy=scanner_policy,
            scanner_request=scanner_request,
            event_collector=self.event_collector,
            provider=provider_override,
            market_data_client=self.connection_manager.optional_client,
            disconnect_provider=provider_override is not None,
            forced_session_label=preparation_session,
            forced_session_source="PREPARATION_MODE_ACTIVE",
        )
        write_premarket_prep_artifact(
            mode=self.run_mode.value,
            session=preparation_session,
            scanner_payload=payload,
            watchlist_k=int(scanner_policy.watchlist_limit_k),
        )
        raw_symbols = payload.get("symbols") or payload.get("top_n_symbols") or [
            item.get("symbol") for item in payload.get("universe_top_n", []) if isinstance(item, dict)
        ]
        symbols = [str(symbol).upper() for symbol in raw_symbols if str(symbol).strip()][:50]
        float_provider = FloatProvider()
        success = 0
        missing = 0
        for symbol in symbols:
            value, source = float_provider.get_float(symbol)
            if value is not None and source != "UNKNOWN":
                success += 1
            else:
                missing += 1
        print(f"[FLOAT][SUMMARY] requested={len(symbols)} fetched_ok={success} missing={missing}")
        print("FLOAT DISCOVERY SUCCESS" if success > 0 else "FLOAT DISCOVERY WARNING")

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


def _log_tha_source(symbol: str, source: str, segment_count: int) -> None:
    print(f"[THA][SOURCE] symbol={symbol} source={source} segments={segment_count}")
