"""
Execution engine that routes through a broker adapter with deterministic retry semantics.
"""

import hashlib
import os
import time
import math
import uuid
from src.core.acquisition import checkpoint
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, List, Optional

from src.brokers.base_broker import BrokerOrderRequest
from src.config.config_resolver import get_config
from src.config.runtime_config import (
    RunMode,
    get_execution_enabled,
    get_ibkr_readonly_enabled,
)
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.capital_management_authority import CapitalDecision, CapitalManagementAuthority
from src.core.daily_risk_governor import DailyRiskGovernor
from src.core.event_collector import EventCollector
from src.core.strategy_capital_allocation_authority import (
    StrategyAllocationDecision,
    StrategyCapitalAllocationAuthority,
)
from src.core.stop_controller import StopController
from src.core.stop_loss_authority import StopAuthorityError, validate_stop_price
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.execution.execution_providers import ExecutionProvider, IbkrExecutionProvider, PaperExecutionProvider
from src.execution.exit_plan import compute_stop_price
from src.execution.order_models import PendingOrderBook
from src.execution.autonomous_recovery_authority import (
    AutonomousRecoveryAuthority,
    AutonomousRecoveryDecision,
)
from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
from src.execution.startup_recovery_authority import (
    RecoveryState,
    StartupRecoveryAuthority,
    StartupRecoveryResult,
)
from src.models.execution_result import ExecutionResult
from src.models.data_models import RiskDecision
from src.models.risk_decision import DECISION_ARTIFACT_MISSING
from src.sim.price_feed import DeterministicPriceFeed, PriceFeed


class ExecutionEngine:
    VALID_IBKR_STATUSES = {
        "Submitted",
        "PreSubmitted",
        "Filled",
        "PendingSubmit",
        "PendingCancel",
    }
    VALID_CACHED_IBKR_STATUSES = {status.upper() for status in VALID_IBKR_STATUSES} | {
        "REJECTED", "CANCELLED", "CANCELED", "INACTIVE"}
    """Deterministic execution engine with broker routing and retry semantics."""

    def __init__(
        self,
        provider: Optional[ExecutionProvider] = None,
        trade_registry: Optional[ActiveTradeRegistry] = None,
        event_collector: Optional[EventCollector] = None,
        price_feed: Optional[PriceFeed] = None,
        stop_controller: Optional[StopController] = None,
        trade_lifecycle_engine: Optional[object] = None,
        storage_engine: Optional[object] = None,
        capital_authority: Optional[CapitalManagementAuthority] = None,
        strategy_allocation_authority: Optional[StrategyCapitalAllocationAuthority] = None,
        daily_risk_governor: Optional[DailyRiskGovernor] = None,
        autonomous_recovery_authority: Optional[AutonomousRecoveryAuthority] = None,
    ) -> None:
        print("[BOOT] ExecutionEngine instantiated — broker-routed deterministic flow")
        self.run_mode: RunMode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        self.runtime_mode_manager = RuntimeModeManager.resolve()
        self.execution_enabled = get_execution_enabled()
        self.max_shares_per_order = self.runtime_mode_manager.max_shares_per_order
        if not self.execution_enabled:
            print("[SAFETY] EXECUTION: HARD DISABLED")
            print("[EXECUTION] Gateway: DISABLED")
            print("[EXECUTION] Liquidity checks: DISABLED")
            print("[EXECUTION] Broker submission: DISABLED")
        elif self.run_mode == RunMode.PAPER:
            print("[SAFETY] PAPER-EXECUTION MODE ACTIVE")
        self.trade_registry = trade_registry or ActiveTradeRegistry()
        self.event_collector = event_collector or EventCollector()
        self.stop_controller = stop_controller or StopController()
        self.price_feed = price_feed or DeterministicPriceFeed()
        self.pending_book = PendingOrderBook()
        self.current_tick: Optional[int] = None
        self._seen_idempotency_keys: set[str] = set()
        self.execution_integrity_flag: bool = False
        self._order_trace_stages: dict[str, set[str]] = {}
        self._require_exit_stage: set[str] = set()
        self.position_records: dict[str, dict] = {}
        self._native_orders: dict[str, dict] = {}
        self._native_scope = None
        self._native_state = None
        self._native_loaded = False
        self._native_quarantined = False
        self._native_processing_results: set[int] = set()
        self._failsafe_block_new_entries: bool = False
        self.startup_recovery_state: RecoveryState = RecoveryState.RECOVERY_PENDING
        self.startup_recovery_result: StartupRecoveryResult | None = None
        self._trade_lifecycle_engine = trade_lifecycle_engine
        self._storage_engine = storage_engine
        self._provider = self._resolve_provider(provider)
        self.post_fill_lifecycle = PostFillLifecycleEngine(
            run_mode=self.run_mode.value,
            execution_provider=self._provider,
            storage_engine=storage_engine,
        )
        self.capital_authority = capital_authority or CapitalManagementAuthority(
            run_mode=self.run_mode.value,
            storage_engine=storage_engine,
        )
        self.strategy_allocation_authority = (
            strategy_allocation_authority
            or StrategyCapitalAllocationAuthority(
                run_mode=self.run_mode.value,
                storage_engine=storage_engine,
            )
        )
        self.daily_risk_governor = daily_risk_governor or DailyRiskGovernor(
            event_collector=self.event_collector,
            storage_engine=storage_engine,
            trade_lifecycle_engine=trade_lifecycle_engine,
            provider=self._provider,
        )
        self.autonomous_recovery_authority = (
            autonomous_recovery_authority
            or AutonomousRecoveryAuthority(event_collector=self.event_collector)
        )
        self._prospective_decisions_by_order_id: dict[str, str] = {}
        self._capital_decisions_by_order_id: dict[str, str] = {}
        self._strategy_allocation_decisions_by_order_id: dict[str, str] = {}
        self.provider: Optional[ExecutionProvider] = self._provider
        self.broker = getattr(self._provider, "broker", None)
        self._recover_startup_state()
        self._recover_capital_state()
        self.daily_risk_governor.recover(
            run_mode=self.run_mode.value,
            recovery_complete=self.startup_recovery_complete(),
            event_collector=self.event_collector,
            storage_engine=storage_engine,
            trade_lifecycle_engine=trade_lifecycle_engine,
            provider=self._provider,
        )

    def bind_native_order_scope(self, *, account, client, as_of) -> None:
        # Existing complete position-snapshot authority, not a caller config flag.
        self._native_scope = (account, client, as_of) if isinstance(account, str) and account.strip() and client is not None else None

    def _save_native_orders(self) -> None:
        from copy import deepcopy
        state = {"version": 1, "mode": self.run_mode.value, "orders": deepcopy(self._native_orders)}
        try:
            self._storage_engine.store_execution_order_state(
                "execution.native_orders.v1:" + self.run_mode.value, state, expected=self._native_state)
            self._native_state = state
        except BaseException:
            self._native_quarantined = True
            self._failsafe_block_new_entries = True
            self._mark_capital_recovery_failed("NATIVE_ORDER_STATE_PERSISTENCE_UNRESOLVED")
            raise

    def _load_native_orders(self) -> None:
        if self._native_loaded:
            if self._native_quarantined:
                raise RuntimeError("NATIVE_ORDER_RECOVERY_REQUIRED")
            return
        store = self._storage_engine
        if (store is None or not getattr(store, "enabled", False) or getattr(store, "backend", None) != "sqlite"
                or not callable(getattr(store, "store_execution_order_state", None))):
            raise RuntimeError("NATIVE_ORDER_STORAGE_UNAVAILABLE")
        state = store.fetch_management_state("execution.native_orders.v1:" + self.run_mode.value)
        self._native_loaded = True
        self._native_state = state
        if state is not None:
            # No process-local accounting/manager effect can be reconstructed from
            # a request snapshot. Restored records are inspection-only, no replay.
            self._native_quarantined = True
            self._failsafe_block_new_entries = True
            if hasattr(self, "post_fill_lifecycle"):
                self._mark_capital_recovery_failed("NATIVE_ORDER_RESTART_RECONCILIATION_REQUIRED")
            raise RuntimeError("NATIVE_ORDER_RESTART_RECONCILIATION_REQUIRED")

    def _native_callback_client(self):
        manager = getattr(self._provider.broker, "connection_manager", None)
        client = getattr(manager, "existing_client", None)
        # Existing test/legacy boundary compatibility, not the live manager API.
        return client if client is not None else getattr(manager, "optional_client", None)

    def _retain_native_request(self, request) -> dict:
        self._load_native_orders()
        scope = self._native_scope
        client = self._native_callback_client()
        if scope is None or scope[1] is not client:
            raise RuntimeError("NATIVE_ORDER_ACCOUNT_SCOPE_UNAVAILABLE")
        from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
        if not 0 <= (datetime.now(timezone.utc) - scope[2]).total_seconds() <= get_ibkr_snapshot_max_age_seconds():
            raise RuntimeError("NATIVE_ORDER_SCOPE_STALE")
        decision = self._prospective_decisions_by_order_id.get(request.client_order_id)
        if (not decision or request.client_order_id in self._native_orders or request.quantity <= 0
                or request.relationship_context or request.direction.upper() not in {"LONG", "BUY"}):
            raise RuntimeError("NATIVE_ORDER_BINDING_INVALID")
        order = {"request": asdict(request), "decision_id": decision, "account": scope[0],
            "mode": self.run_mode.value, "symbol": request.symbol.upper(), "side": request.direction.upper(), "requested": request.quantity, "filled": 0, "notional": 0.,
            "terminal": False, "status": "DISPATCH_UNCERTAIN", "broker_order_id": None}
        self._native_orders[request.client_order_id] = order
        self._save_native_orders()  # Before dispatch; lost ack never implies absence.
        return order

    def _execution_log(self, stage: str, **payload: object) -> None:
        fields = []
        for key, value in payload.items():
            if value is None:
                continue
            fields.append(f"{key}={value}")
        suffix = f" {' '.join(fields)}" if fields else ""
        print(f"[EXECUTION][{stage}]{suffix}")

    def _resolve_provider(
        self, provider: Optional[ExecutionProvider]
    ) -> Optional[ExecutionProvider]:
        if not self.execution_enabled:
            return None
        if self.run_mode == RunMode.PAPER:
            if isinstance(provider, IbkrExecutionProvider):
                print("[EXECUTION][PAPER] IBKR paper submission provider active")
                return provider
            if provider is not None and not isinstance(provider, PaperExecutionProvider):
                print("[EXECUTION][PAPER] Unsupported provider type; falling back to PaperExecutionProvider")
            return provider if isinstance(provider, PaperExecutionProvider) else PaperExecutionProvider(
                price_feed=self.price_feed,
                trade_registry=self.trade_registry,
                event_collector=self.event_collector,
                run_mode=self.run_mode,
            )
        if provider is None:
            raise RuntimeError(
                "Execution provider missing in live execution mode. "
                "Verify TWS/Gateway connectivity, unified runtime authority allows orders, "
                "IBKR_ORDER_SUBMISSION_ENABLED=true, IBKR_READONLY_ENABLED=false, and IBKR_LIVE_PORT=7496."
            )
        return provider

    def _recover_startup_state(self) -> None:
        authority = StartupRecoveryAuthority(
            run_mode=self.run_mode.value,
            provider=self._provider,
            post_fill_lifecycle=self.post_fill_lifecycle,
            trade_registry=self.trade_registry,
            trade_lifecycle_engine=self._trade_lifecycle_engine,
        )
        result = authority.run()
        self.startup_recovery_state = result.state
        self.startup_recovery_result = result
        self._failsafe_block_new_entries = result.state != RecoveryState.RECOVERY_COMPLETE
        if hasattr(self.post_fill_lifecycle, "set_startup_recovery_complete"):
            self.post_fill_lifecycle.set_startup_recovery_complete(
                result.state == RecoveryState.RECOVERY_COMPLETE
            )
        provider_name = self._provider.name() if self._provider is not None else "NONE"
        print(
            "[RECOVERY][STARTUP] "
            f"provider={provider_name} state={result.state.value} "
            f"open_positions={result.positions_count} open_orders={result.orders_count}"
        )

    def startup_recovery_complete(self) -> bool:
        return self.startup_recovery_state == RecoveryState.RECOVERY_COMPLETE

    def startup_recovery_block_reason(self) -> str:
        if self.startup_recovery_result is not None and self.startup_recovery_result.reason:
            return str(self.startup_recovery_result.reason)
        return self.startup_recovery_state.value

    def _recover_capital_state(self) -> None:
        if not self.startup_recovery_complete():
            return
        if getattr(self.capital_authority, 'capital_scope', None) is not None:
            # Enrolled capital is restored by read-only authoritative load.
            # Never use this legacy rebuild route for any related effect owner.
            self.capital_authority._capital_projection()
            if self.capital_authority.recovery_failed:
                self._mark_capital_recovery_failed(self.capital_authority.recovery_failure_reason)
            return
        lifecycle_trades: list[object] = []
        if self._trade_lifecycle_engine is not None:
            getter = getattr(self._trade_lifecycle_engine, "get_open_lifecycle_trades", None)
            if callable(getter):
                lifecycle_trades = list(getter() or [])
        if not lifecycle_trades:
            lifecycle_trades = list(getattr(self.post_fill_lifecycle, "_trades", {}).values())
        self.strategy_allocation_authority.recover_from_lifecycle(lifecycle_trades)
        self.capital_authority.recover_from_lifecycle(lifecycle_trades)

        broker_orders: list[object] = []
        if self._provider is not None:
            try:
                broker_orders = list(self._provider.get_open_orders() or [])
                self._relationship_open_orders = broker_orders
                self._relationship_orders_asof = datetime.now(timezone.utc)
            except Exception as exc:
                if self.run_mode == RunMode.LIVE:
                    self._mark_capital_recovery_failed(f"CAPITAL_OPEN_ORDER_RECOVERY_FAILED:{exc}")
                return
        self.capital_authority.recover_from_open_orders(broker_orders)
        if self.run_mode == RunMode.LIVE and getattr(self.capital_authority, "recovery_failed", False):
            reason = getattr(self.capital_authority, "recovery_failure_reason", "CAPITAL_RECOVERY_FAILED")
            self._mark_capital_recovery_failed(str(reason))

    def _mark_capital_recovery_failed(self, reason: str) -> None:
        self.startup_recovery_state = RecoveryState.RECOVERY_FAILED
        self.startup_recovery_result = StartupRecoveryResult(
            state=RecoveryState.RECOVERY_FAILED,
            reason=reason,
        )
        self._failsafe_block_new_entries = True
        if hasattr(self.post_fill_lifecycle, "set_startup_recovery_complete"):
            self.post_fill_lifecycle.set_startup_recovery_complete(False)
        print(f"[CAPITAL][RECOVER] status=FAILED reason={reason}")

    def _strategy_allocation_admission_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        direction = str(getattr(risk_decision, "direction", "") or "").upper()
        if direction not in {"BUY", "LONG", "SHORT"}:
            return None
        account = self._capital_account_snapshot(risk_decision)
        context = self._strategy_allocation_context(risk_decision)
        requested_quantity = self._effective_quantity_from_risk_decision(risk_decision)
        decision = self.strategy_allocation_authority.evaluate_entry(
            run_mode=self.run_mode.value,
            strategy_id=getattr(risk_decision, "strategy_name", None) or "UNKNOWN",
            symbol=risk_decision.symbol,
            side=direction,
            requested_quantity=requested_quantity,
            reference_price=float(getattr(risk_decision, "entry_price", 0.0) or 0.0),
            available_capital=account.get("available_capital"),
            account_equity=account.get("account_equity"),
            current_strategy_exposure=context["current_strategy_exposure"],
            current_strategy_open_positions=context["current_strategy_open_positions"],
            current_symbol_position_exists=bool(context["current_symbol_position_exists"]),
            strategy_daily_trade_count=context["strategy_daily_trade_count"],
            recovery_complete=self.startup_recovery_complete(),
            broker_truth_available=bool(account["broker_truth_available"]),
            intent_id=getattr(risk_decision, "intent_id", None),
            reserve=True,
            audit_payload={
                "risk_decision_id": getattr(risk_decision, "decision_id", None),
                "intent_id": getattr(risk_decision, "intent_id", None),
                "trader_type": getattr(risk_decision, "trader_type", None),
            },
        )
        risk_decision.strategy_allocation_decision = decision
        risk_decision.strategy_allocation_decision_id = decision.decision_id
        if not decision.executable:
            print(
                "[STRATEGY_ALLOC][BLOCKED] "
                f"strategy_id={decision.strategy_id} symbol={risk_decision.symbol} "
                f"status={decision.status.value} reason={decision.reason}"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"STRATEGY_ALLOC_{decision.status.value}:{decision.reason}",
            )
        if decision.approved_quantity < int(getattr(risk_decision, "max_position_size", 0) or 0):
            risk_decision.max_position_size = decision.approved_quantity
        return None

    def _strategy_allocation_context(self, risk_decision: RiskDecision) -> dict[str, float | int | bool]:
        strategy_id = str(getattr(risk_decision, "strategy_name", "") or "UNKNOWN").upper()
        symbol = str(getattr(risk_decision, "symbol", "") or "").upper()
        strategy_exposure = 0.0
        strategy_open_positions = 0
        current_symbol_position_exists = False
        injected_lifecycle_trades, post_fill_lifecycle_trades = self._strategy_allocation_lifecycle_sources()
        lifecycle_trades = injected_lifecycle_trades or post_fill_lifecycle_trades
        if lifecycle_trades:
            for trade in lifecycle_trades:
                trade_strategy = self._lifecycle_trade_strategy_id(trade)
                if trade_strategy != strategy_id:
                    continue
                qty = self._lifecycle_trade_open_quantity(trade)
                price = self._lifecycle_trade_entry_price(trade)
                if qty <= 0:
                    continue
                strategy_open_positions += 1
                strategy_exposure += float(qty) * price
                if str(getattr(trade, "symbol", "") or "").upper() == symbol:
                    current_symbol_position_exists = True
            if not current_symbol_position_exists:
                current_symbol_position_exists = self._lifecycle_sources_have_symbol_position(
                    strategy_id,
                    symbol,
                    injected_lifecycle_trades + post_fill_lifecycle_trades,
                )
        else:
            for trade in self.trade_registry.snapshot():
                trade_strategy = str(getattr(trade, "strategy_name", "") or "UNKNOWN").upper()
                if trade_strategy != strategy_id:
                    continue
                qty = int(getattr(trade, "quantity", 0) or 0)
                price = float(getattr(trade, "entry_price", 0.0) or 0.0)
                if qty <= 0:
                    continue
                strategy_open_positions += 1
                strategy_exposure += float(qty) * price
                if str(getattr(trade, "symbol", "") or "").upper() == symbol:
                    current_symbol_position_exists = True
        return {
            "current_strategy_exposure": strategy_exposure,
            "current_strategy_open_positions": strategy_open_positions,
            "current_symbol_position_exists": current_symbol_position_exists,
            "strategy_daily_trade_count": 0,
        }

    def _strategy_allocation_lifecycle_sources(self) -> tuple[list[object], list[object]]:
        injected_trades: list[object] = []
        if self._trade_lifecycle_engine is not None:
            getter = getattr(self._trade_lifecycle_engine, "get_open_lifecycle_trades", None)
            if callable(getter):
                injected_trades = list(getter() or [])

        return injected_trades, self._post_fill_lifecycle_open_trades()

    def _lifecycle_sources_have_symbol_position(
        self,
        strategy_id: str,
        symbol: str,
        lifecycle_trades: list[object],
    ) -> bool:
        for trade in lifecycle_trades:
            if self._lifecycle_trade_strategy_id(trade) != strategy_id:
                continue
            if self._lifecycle_trade_open_quantity(trade) <= 0:
                continue
            if str(getattr(trade, "symbol", "") or "").upper() == symbol:
                return True
        return False

    def _post_fill_lifecycle_open_trades(self) -> list[object]:
        trades = list(getattr(self.post_fill_lifecycle, "_trades", {}).values())
        return [trade for trade in trades if self._is_open_lifecycle_trade(trade)]

    @staticmethod
    def _lifecycle_trade_strategy_id(trade: object) -> str:
        return str(
            getattr(trade, "strategy_name", None)
            or getattr(trade, "strategy_id", None)
            or "UNKNOWN"
        ).upper()

    @staticmethod
    def _lifecycle_trade_open_quantity(trade: object) -> int:
        quantity_open = getattr(trade, "quantity_open", None)
        if quantity_open is not None:
            return int(quantity_open or 0)
        filled_qty = int(getattr(trade, "filled_qty", 0) or 0)
        exited_qty = int(getattr(trade, "exited_qty", 0) or 0)
        return max(0, filled_qty - exited_qty)

    @staticmethod
    def _lifecycle_trade_entry_price(trade: object) -> float:
        return float(
            getattr(trade, "entry_avg_price", None)
            or getattr(trade, "avg_fill_price", None)
            or getattr(trade, "entry_price", 0.0)
            or 0.0
        )

    @classmethod
    def _is_open_lifecycle_trade(cls, trade: object) -> bool:
        state = getattr(trade, "state", None)
        state_value = str(getattr(state, "value", state) or "").upper()
        if state_value in {"EXITED", "LIFECYCLE_FAILURE", "CLOSED"}:
            return False
        return cls._lifecycle_trade_open_quantity(trade) > 0

    def _capital_admission_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        direction = str(getattr(risk_decision, "direction", "") or "").upper()
        if direction not in {"BUY", "LONG", "SHORT"}:
            return None
        account = self._capital_account_snapshot(risk_decision)
        context = self._capital_portfolio_context(risk_decision.symbol)
        requested_quantity = self._effective_quantity_from_risk_decision(risk_decision)
        decision = self.capital_authority.evaluate_entry(
            run_mode=self.run_mode.value,
            strategy_id=getattr(risk_decision, "strategy_name", None) or "UNKNOWN",
            symbol=risk_decision.symbol,
            side=direction,
            requested_quantity=requested_quantity,
            reference_price=float(getattr(risk_decision, "entry_price", 0.0) or 0.0),
            account_equity=account.get("account_equity"),
            available_capital=account.get("available_capital"),
            buying_power=account.get("buying_power"),
            current_total_exposure=context["current_total_exposure"],
            current_symbol_exposure=context["current_symbol_exposure"],
            current_open_positions=context["current_open_positions"],
            current_symbol_position_exists=bool(context["current_symbol_position_exists"]),
            max_open_positions=self._evaluated_limit(risk_decision, "max_open_positions"),
            max_position_notional=self._evaluated_limit(risk_decision, "max_position_notional"),
            max_total_exposure=self._evaluated_limit(risk_decision, "max_total_exposure"),
            max_symbol_exposure=self._evaluated_limit(risk_decision, "max_symbol_exposure"),
            recovery_complete=self.startup_recovery_complete(),
            risk_approved=bool(getattr(risk_decision, "allowed", False)),
            broker_truth_available=account["broker_truth_available"],
            intent_id=getattr(risk_decision, "intent_id", None),
            reserve=True,
            audit_payload={
                "risk_decision_id": getattr(risk_decision, "decision_id", None),
                "intent_id": getattr(risk_decision, "intent_id", None),
                "trader_type": getattr(risk_decision, "trader_type", None),
            },
        )
        risk_decision.capital_decision = decision
        risk_decision.capital_decision_id = decision.decision_id
        if not decision.executable:
            print(
                "[CAPITAL][BLOCKED] "
                f"symbol={risk_decision.symbol} status={decision.status.value} reason={decision.reason}"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"CAPITAL_{decision.status.value}:{decision.reason}",
            )
        if decision.approved_quantity < int(getattr(risk_decision, "max_position_size", 0) or 0):
            strategy_decision_id = getattr(risk_decision, "strategy_allocation_decision_id", None)
            if strategy_decision_id:
                self.strategy_allocation_authority.resize_reservation(
                    decision_id=strategy_decision_id,
                    quantity=decision.approved_quantity,
                    notional=decision.approved_notional,
                    reason="P7_CAPITAL_REDUCED",
                )
            risk_decision.max_position_size = decision.approved_quantity
        return None

    def _capital_portfolio_context(self, symbol: str) -> dict[str, float | int]:
        total_exposure = 0.0
        symbol_exposure = 0.0
        symbol_position_exists = False
        open_positions = self.trade_registry.count_active()
        lifecycle_trades: list[object] = []
        if self._trade_lifecycle_engine is not None:
            getter = getattr(self._trade_lifecycle_engine, "get_open_lifecycle_trades", None)
            if callable(getter):
                lifecycle_trades = list(getter() or [])
        if lifecycle_trades:
            open_positions = len(lifecycle_trades)
            for trade in lifecycle_trades:
                qty = int(getattr(trade, "quantity_open", 0) or 0)
                price = float(getattr(trade, "entry_avg_price", 0.0) or 0.0)
                notional = float(qty) * price
                total_exposure += notional
                if str(getattr(trade, "symbol", "") or "").upper() == str(symbol or "").upper():
                    symbol_position_exists = symbol_position_exists or qty > 0
                    symbol_exposure += notional
        else:
            for trade in self.trade_registry.snapshot():
                qty = int(getattr(trade, "quantity", 0) or 0)
                price = float(getattr(trade, "entry_price", 0.0) or 0.0)
                notional = float(qty) * price
                total_exposure += notional
                if str(getattr(trade, "symbol", "") or "").upper() == str(symbol or "").upper():
                    symbol_position_exists = symbol_position_exists or qty > 0
                    symbol_exposure += notional
        return {
            "current_total_exposure": total_exposure,
            "current_symbol_exposure": symbol_exposure,
            "current_open_positions": open_positions,
            "current_symbol_position_exists": symbol_position_exists,
        }

    def _capital_account_snapshot(self, risk_decision: RiskDecision) -> dict[str, float | bool | None]:
        evaluated = getattr(risk_decision, "evaluated_limits", {}) or {}
        equity = self._float_or_none(
            evaluated.get("account_equity")
            or evaluated.get("equity")
            or evaluated.get("net_liquidation")
        )
        available = self._float_or_none(
            evaluated.get("available_capital")
            or evaluated.get("available_funds")
            or evaluated.get("AvailableFunds")
        )
        buying_power = self._float_or_none(evaluated.get("buying_power") or evaluated.get("BuyingPower"))
        truth_available = equity is not None and available is not None and buying_power is not None
        if truth_available:
            return {
                "account_equity": equity,
                "available_capital": available,
                "buying_power": buying_power,
                "broker_truth_available": True,
            }
        for source in (
            self._provider,
            getattr(self._provider, "broker", None) if self._provider is not None else None,
            getattr(getattr(self._provider, "broker", None), "client", None) if self._provider is not None else None,
        ):
            summary = self._read_account_summary(source)
            if not summary:
                continue
            equity = self._float_or_none(
                summary.get("NetLiquidation")
                or summary.get("net_liquidation")
                or summary.get("account_equity")
                or summary.get("equity")
            )
            available = self._float_or_none(
                summary.get("AvailableFunds")
                or summary.get("available_funds")
                or summary.get("available_capital")
            )
            buying_power = self._float_or_none(summary.get("BuyingPower") or summary.get("buying_power"))
            if equity is not None and available is not None and buying_power is not None:
                return {
                    "account_equity": equity,
                    "available_capital": available,
                    "buying_power": buying_power,
                    "broker_truth_available": True,
                }
        return {
            "account_equity": None,
            "available_capital": None,
            "buying_power": None,
            "broker_truth_available": False,
        }

    @staticmethod
    def _read_account_summary(source: object | None) -> dict:
        if source is None:
            return {}
        method = getattr(source, "get_account_summary", None)
        if callable(method):
            try:
                summary = method()
            except Exception:
                return {}
            return dict(summary or {}) if isinstance(summary, dict) else {}
        summary = getattr(source, "account_summary", None)
        return dict(summary or {}) if isinstance(summary, dict) else {}

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _evaluated_limit(risk_decision: RiskDecision, name: str) -> float | int | None:
        evaluated = getattr(risk_decision, "evaluated_limits", {}) or {}
        value = evaluated.get(name)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def refresh_relationship_order_snapshot(self) -> None:
        """Reuse fresh canonical orders, refreshing expired active-plan evidence."""
        manager = getattr(self, "relationship_manager", None)
        if manager is None or not manager._relationship_plans or self._provider is None:
            return
        plans = list(manager._relationship_plans.values())
        if not manager.snapshot_positions() and not any(p.pending_stop_cancel or any(not o["terminal"] for o in p.orders.values()) for p in plans):
            return
        from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
        now = datetime.now(timezone.utc)
        stamp = getattr(self, "_relationship_orders_asof", None)
        if stamp and 0 <= (now - stamp).total_seconds() <= get_ibkr_snapshot_max_age_seconds() and not any(p.pending_stop_cancel or p.pending_stop_resize for p in plans):
            return
        self._relationship_orders_asof = None
        try:
            orders = list(self._provider.get_open_orders() or [])
        except Exception:
            return  # stale evidence cannot reconcile a restored plan
        self._relationship_open_orders = orders
        self._relationship_orders_asof = datetime.now(timezone.utc)
        self._bind_owned_reduction_identities(orders)
        def read(row, key):
            return row.get(key) if isinstance(row, dict) else getattr(row, key, None)
        active_ids = {str(read(o, "order_id")) for o in orders
                      if str(read(o, "status") or "").upper() not in {"CANCELLED", "CANCELED", "FILLED", "INACTIVE"}}
        cleaned = self._confirm_relationship_stop_resizes(orders)
        for plan in plans:
            if plan.pending_stop_cancel and plan.pending_stop_cancel not in active_ids:
                plan.pending_stop_cancel = None
                cleaned = True
        if cleaned:
            manager._save_relationship_state()
            self._run_protection_reconciliation(open_orders=orders, reason="relationship_stop_cleanup")

    def _bind_owned_reduction_identities(self, orders: list[object]) -> None:
        """Bind a late native identity only to one exact retained owned request."""
        from numbers import Number
        manager = self.relationship_manager
        def read(row, key):
            return row.get(key) if isinstance(row, dict) else getattr(row, key, None)
        for plan in manager._relationship_plans.values():
            for action_id, owned in plan.orders.items():
                request = owned.get("request")
                if owned["action"] != "REDUCE" or owned["terminal"] or owned.get("broker_order_id") or not request:
                    continue
                context = request.get("relationship_context") or {}
                if (request.get("client_order_id") != action_id or request.get("symbol") != plan.symbol
                        or request.get("direction") != "SELL" or request.get("quantity") != owned["requested"]
                        or context.get("relationship_id") != plan.relationship_id
                        or context.get("management_action_id") != action_id or context.get("action") != "REDUCE"):
                    continue
                candidates = [row for row in orders if (read(row, "metadata") or {}).get("order_ref") == action_id]
                if len(candidates) != 1:
                    continue
                matches = []
                for row in candidates:
                    metadata = read(row, "metadata") or {}
                    quantity = metadata.get("native_quantity")
                    con_id = metadata.get("con_id")
                    if (str(read(row, "symbol") or "").upper() != plan.symbol
                            or metadata.get("order_ref") != action_id
                            or str(metadata.get("side") or "").upper() != "SELL"
                            or str(read(row, "order_type") or "").upper() != str(request.get("order_type") or "").upper()
                            or type(con_id) is not int or plan.security_id != f"conId:{con_id}"
                            or isinstance(quantity, bool) or not isinstance(quantity, Number)
                            or not math.isfinite(quantity) or quantity != owned["requested"]
                            or str(read(row, "status") or "").upper() not in {"SUBMITTED", "PRESUBMITTED", "PENDINGSUBMIT", "PENDINGCANCEL"}
                            or not str(read(row, "order_id") or "").isdigit()
                            or int(read(row, "order_id")) <= 0):
                        continue
                    matches.append(str(read(row, "order_id")))
                if (len(matches) == 1
                        and sum(str(read(row, "order_id")) == matches[0] for row in orders) == 1
                        and not any(str(other_plan.protection_broker_order_id) == matches[0]
                            for other_plan in manager._relationship_plans.values())
                        and not any(other.get("broker_order_id") == matches[0]
                        for other_plan in manager._relationship_plans.values() for other in other_plan.orders.values())):
                    owned["broker_order_id"] = matches[0]
                    manager._save_relationship_state()
            manager.cancel_excess_milestone_orders(plan)

    def _confirmed_stop_quantity(self, *, symbol, life, orders: list[object], stop_filled=0) -> float | None:
        # Shared canonical snapshot rule for existing resize confirmation and
        # active relationship management; never query or infer an acknowledgement.
        if life is None or life.stop is None:
            return None
        def read(row, key):
            return row.get(key) if isinstance(row, dict) else getattr(row, key, None)
        matches = [o for o in orders if str(read(o, "order_id")) == str(life.stop.broker_order_id)
                   and str(read(o, "symbol") or "").upper() == symbol
                   and str(read(o, "status") or "").upper() in {"SUBMITTED", "PRESUBMITTED"}]
        if len(matches) != 1:
            return None
        metadata = read(matches[0], "metadata") or {}
        if any(isinstance(metadata.get(key), bool) for key in ("quantity", "stop_price")):
            return None
        quantity = self._float_or_none(metadata.get("quantity"))
        price = self._float_or_none(metadata.get("stop_price"))
        if (quantity is not None and math.isfinite(quantity) and quantity - stop_filled == life.filled_qty
                and str(metadata.get("side") or "").upper() == "SELL"
                and price is not None and math.isfinite(price) and price >= life.stop.trigger_price):
            return quantity
        return None

    def _confirmed_relationship_stop_quantity(self, plan, life, orders: list[object]) -> float | None:
        filled = plan.orders.get(f"{plan.relationship_id}:stop:{life.stop.broker_order_id}", {}).get("filled", 0) if life and life.stop else 0
        return self._confirmed_stop_quantity(symbol=plan.symbol, life=life, orders=orders, stop_filled=filled)

    def relationship_protection_confirmed(self, plan) -> bool:
        life = self.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
        return self._confirmed_relationship_stop_quantity(plan, life,
            getattr(self, "_relationship_open_orders", [])) is not None

    def _confirm_relationship_stop_resizes(self, orders: list[object]) -> bool:
        manager = getattr(self, "relationship_manager", None)
        if manager is None:
            return False
        changed = False
        for plan in manager._relationship_plans.values():
            if not plan.pending_stop_resize:
                continue
            life = self.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
            quantity = self._confirmed_relationship_stop_quantity(plan, life, orders)
            if quantity is not None:
                plan.pending_stop_resize = False
                life.stop.quantity = int(quantity)
                changed = True
                manager._save_relationship_state()
        return changed

    def _run_protection_reconciliation(self, *, open_orders: list[object] | None = None, reason: str = "runtime") -> None:
        if self._provider is None:
            return
        try:
            broker_orders = list(open_orders) if open_orders is not None else list(self._provider.get_open_orders())
        except Exception as exc:
            print(f"[LIFECYCLE][RECONCILIATION][ERROR] stage=fetch_open_orders reason={exc}")
            return
        self._relationship_open_orders = broker_orders
        self._relationship_orders_asof = datetime.now(timezone.utc)
        summary = self.post_fill_lifecycle.reconcile_orders(broker_orders, repair=True)
        self._confirm_relationship_stop_resizes(broker_orders)
        manager = getattr(self, "relationship_manager", None)
        unresolved = any(p.pending_stop_resize or p.pending_stop_cancel or any(
            o.get("lifecycle_application_rejected") or o.get("cached_update_in_progress") or o.get("owner_effect_pending") for o in p.orders.values())
            for p in manager._relationship_plans.values()) if manager else False
        self._failsafe_block_new_entries = bool(summary.get("block_new_entries", False)) or unresolved or self._native_quarantined or any(o.get("cached_update_in_progress") or not o.get("broker_order_id") or o.get("quarantine") for o in self._native_orders.values())
        print(
            "[LIFECYCLE][RECONCILIATION][SUMMARY] "
            f"stage={reason} findings={len(summary.get('findings', []))} repaired={summary.get('repaired', 0)} "
            f"orphans={len(summary.get('orphan_orders', []))} block_new_entries={self._failsafe_block_new_entries}"
        )

    @staticmethod
    def _max_attempts(trader_type: str) -> int:
        normalized = (trader_type or "").upper()
        limits = get_config("EXECUTION_MAX_ATTEMPTS_BY_TRADER")
        if normalized in limits:
            return int(limits[normalized])
        return int(limits.get("DEFAULT", 1))

    @staticmethod
    def _client_order_id(
        symbol: str, trader_type: str, strategy_name: str, direction: str, created_tick: int
    ) -> str:
        key = f"{symbol}|{trader_type}|{strategy_name}|{direction}|{created_tick}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def process_pending_orders(self, tick: int) -> List[ExecutionResult]:
        due_orders = self.pending_book.due_orders(tick)
        results: List[ExecutionResult] = []
        if due_orders:
            print(f"[PENDING] Processing {len(due_orders)} pending orders for tick={tick}")
        for order in due_orders:
            self.pending_book.remove(order.client_order_id)
            results.append(self._route_order(order))
        return results

    def execute(self, intents: list[object]) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for intent in intents or []:
            normalized = self._risk_decision_from_intent(intent)
            if normalized is None:
                continue
            results.append(self.execute_trade(normalized))
        return results

    def _risk_decision_from_intent(self, intent: object) -> Optional[RiskDecision]:
        action = str(getattr(intent, "action", "") or "").upper()
        if action not in {"EXIT", "ADD"}:
            return None
        strategy = str(getattr(intent, "strategy_name", "") or "").upper()
        if action == "ADD" and "ROSS" in strategy:
            # Ross exposure must arrive as an actual RiskDecision, never a
            # management label converted into permission and a synthetic stop.
            print("[EXECUTION][BLOCK] reason=ROSS_ADD_REQUIRES_RISK_DECISION")
            return None
        symbol = str(getattr(intent, "symbol", "") or "").upper()
        quantity = int(getattr(intent, "quantity", 0) or 0)
        if not symbol or quantity <= 0:
            return None
        side = "SELL" if action == "EXIT" else "BUY"
        reason = str(getattr(intent, "reason", "") or "TRADE_MANAGEMENT")
        decision_id = f"mgmt-{action.lower()}-{symbol}-{uuid.uuid4().hex[:8]}"
        tick = self.current_tick if self.current_tick is not None else 0
        price = float(self.price_feed.price_for(symbol, tick))
        stop_loss_price = price - 0.01 if side == "BUY" else price + 0.01
        return RiskDecision(
            symbol=symbol,
            allowed=True,
            max_position_size=quantity,
            risk_level="LOW",
            rationale=f"TRADE_MANAGEMENT:{reason}",
            trader_type="MANUAL",
            strategy_name="TRADE_MANAGEMENT",
            direction=side,
            stop_loss_price=stop_loss_price,
            take_profit_price=None,
            reason_code=f"TRADE_MANAGEMENT_{action}",
            decision_id=decision_id,
            intent_id=f"{decision_id}:{datetime.now(timezone.utc).isoformat()}",
            relationship_context=({"relationship_id": intent.relationship_id,
                "management_action_id": intent.management_action_id, "action": "REDUCE"}
                if getattr(intent, "relationship_id", None) else None),
        )

    def execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
        result = self._execute_trade(risk_decision)
        context = getattr(risk_decision, "relationship_context", None) or {}
        manager = getattr(self, "relationship_manager", None)
        plan = manager._relationship_plans.get(context.get("relationship_id")) if manager else None
        action_id = context.get("management_action_id")
        order = plan.orders.get(action_id) if plan and action_id else None
        if order is not None and not order.get("request") and not order.get("broker_order_id") and not result.attempted:
            # Definitive pre-dispatch rejection is distinct from uncertain submit.
            result.relationship_context = {**context, "pre_dispatch_blocked": True}
            result.client_order_id = action_id
            manager.on_relationship_order_update(relationship_id=plan.relationship_id, order_id=action_id,
                cumulative_quantity=order["filled"], average_price=None, terminal=True, status="PRE_DISPATCH_BLOCKED")
        return result

    def _execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
        """
        Convert a risk decision into a broker request and route through the broker adapter.
        """

        self._execution_log(
            "INTENT_RECEIVED",
            symbol=getattr(risk_decision, "symbol", "UNKNOWN") if risk_decision else "UNKNOWN",
            intent_id=getattr(risk_decision, "intent_id", None) if risk_decision else None,
            strategy_id=getattr(risk_decision, "strategy_name", None) if risk_decision else None,
            run_mode=self.run_mode.value,
            side=getattr(risk_decision, "direction", None) if risk_decision else None,
            qty=getattr(risk_decision, "max_position_size", None) if risk_decision else None,
            entry_price=getattr(risk_decision, "entry_price", None) if risk_decision else None,
            order_type="MKT",
        )
        if risk_decision is not None:
            action = "SUBMIT" if getattr(risk_decision, 'allowed', False) else "SKIP"
            reason = getattr(risk_decision, 'rationale', None) or getattr(risk_decision, 'reason_code', None) or 'NO_REASON'
            print(f"[EXECUTION] symbol={risk_decision.symbol} action={action} reason={reason}")
            broker_state = "UNAVAILABLE"
            broker = getattr(self._provider, "broker", None) if self._provider is not None else None
            if broker is not None and hasattr(broker, "health"):
                try:
                    broker_state = "CONNECTED" if bool((broker.health() or {}).get("connected", False)) else "DISCONNECTED"
                except Exception:
                    broker_state = "DEGRADED"
            elif self._provider is not None:
                broker_state = "SIMULATED_PROVIDER"
            print(f"[EXECUTION][MODE] mode={self.run_mode.value} broker_connection_state={broker_state}")
        if risk_decision is None:
            print("[EXECUTION] No execution performed — placeholder path")
            return ExecutionResult(
                symbol="UNKNOWN",
                trader_type="MANUAL",
                attempted=False,
                status="SKIPPED",
                rationale="No risk decision provided; nothing to execute in teaching mode.",
            )

        if (self.run_mode == RunMode.PAPER and self._provider is not None and self._provider.is_live()
                and str(risk_decision.direction).upper() in {"LONG", "BUY", "SHORT"}):
            try:
                self._load_native_orders()  # Before any new admission/reservation, even without a scope.
            except RuntimeError:
                return self._blocked_execution_from_risk_decision(risk_decision, rationale="NATIVE_ORDER_RECOVERY_OR_STORAGE_BLOCKED")
        if self.startup_recovery_complete():
            daily_risk_result = self._daily_risk_preflight_check(risk_decision)
            if daily_risk_result is not None:
                return daily_risk_result

        autonomous_recovery_result = self._autonomous_recovery_preflight_check(risk_decision)
        if autonomous_recovery_result is not None:
            return autonomous_recovery_result

        tick = self.current_tick if self.current_tick is not None else 0
        if getattr(risk_decision, "entry_price", None) is None:
            risk_decision.entry_price = self.price_feed.price_for(risk_decision.symbol, tick)
        if self.run_mode in {RunMode.PAPER, RunMode.LIVE} and getattr(risk_decision, "stop_loss_price", None) is None:
            fallback_stop = getattr(risk_decision, "invalidation_level", None)
            if fallback_stop is None and getattr(risk_decision, "entry_price", None) is not None:
                fallback_stop = compute_stop_price(
                    float(risk_decision.entry_price),
                    str(getattr(risk_decision, "direction", "LONG") or "LONG"),
                    pattern_name=getattr(risk_decision, "pattern_name", None),
                    strategy_name=getattr(risk_decision, "strategy_name", None),
                )
            risk_decision.stop_loss_price = fallback_stop

        idempotency_key = self._resolve_idempotency_key(risk_decision, tick)
        if self._is_duplicate(idempotency_key):
            return self._duplicate_result(risk_decision, idempotency_key)
        risk_decision.idempotency_key = idempotency_key

        if any(not o["terminal"] and o["symbol"] == risk_decision.symbol.upper() for o in self._native_orders.values()):
            return self._blocked_execution_from_risk_decision(risk_decision, rationale="NATIVE_ORDER_UNRESOLVED")
        preflight_result = self._preflight_check(risk_decision)
        if preflight_result is not None:
            return preflight_result

        gate_result = self._session_gate_check(risk_decision)
        if gate_result is not None:
            return gate_result

        strategy_allocation_result = self._strategy_allocation_admission_check(risk_decision)
        if strategy_allocation_result is not None:
            return strategy_allocation_result

        capital_result = self._capital_admission_check(risk_decision)
        if capital_result is not None:
            self._release_strategy_allocation_for_decision(risk_decision, reason="P7_CAPITAL_BLOCKED")
            return capital_result

        order = self._order_from_risk_decision(risk_decision, tick)
        required_fields_check = self._validate_required_order_fields(risk_decision, order)
        if required_fields_check is not None:
            self._release_strategy_allocation_for_order(order, reason="ORDER_FIELD_VALIDATION_FAILED")
            self._release_capital_for_order(order, reason="ORDER_FIELD_VALIDATION_FAILED")
            return required_fields_check
        return self._route_order(order)

    def _session_gate_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        if os.getenv("TEST_PIPELINE_MODE") == "LIVE":
            print("[EXECUTION] test_pipeline_override=True")
            return None

        if self.run_mode == RunMode.PAPER:
            return None

        # THA controls time eligibility in orchestrator; execution no longer applies
        # independent session/prep-only vetoes.
        print("[EXECUTION][SESSION_GATE] bypassed authority=THA")
        return None

    def force_flatten_symbol(self, symbol: str, *, reason: str) -> None:
        normalized = str(symbol or "").upper()
        if not normalized:
            return
        print(f"[EXECUTION][FORCE_FLAT] symbol={normalized} reason={reason}")
        self.event_collector.emit(
            event_type="FORCE_FLAT_REQUESTED",
            source="ExecutionEngine",
            payload={"symbol": normalized, "reason": reason},
        )

    @staticmethod
    def _execution_context(risk_decision: RiskDecision) -> dict:
        evaluated = getattr(risk_decision, "evaluated_limits", {}) or {}
        session = str(evaluated.get("session") or "UNKNOWN").upper()
        execution_allowed = bool(evaluated.get("execution_allowed", True))
        execution_ready = bool(evaluated.get("execution_ready", True))
        prep_only = bool(evaluated.get("prep_only", False))
        return {
            "session": session,
            "execution_allowed": execution_allowed,
            "execution_ready": execution_ready,
            "prep_only": prep_only,
        }

    def _preflight_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        broker = getattr(self._provider, "broker", None)
        provider_ready = self._provider is not None
        broker_connected = True
        if broker is not None and hasattr(broker, "health"):
            try:
                health = broker.health()
                broker_connected = bool(health.get("connected", True))
            except Exception:
                broker_connected = False
        self._execution_log(
            "PRECHECK",
            symbol=risk_decision.symbol,
            intent_id=getattr(risk_decision, "intent_id", None),
            strategy_id=getattr(risk_decision, "strategy_name", None),
            run_mode=self.run_mode.value,
            side=getattr(risk_decision, "direction", None),
            qty=getattr(risk_decision, "max_position_size", None),
            execution_enabled=self.execution_enabled,
            broker_ready=provider_ready,
            broker_connected=broker_connected,
        )
        if not self.startup_recovery_complete():
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"STARTUP_RECOVERY_NOT_COMPLETE:{self.startup_recovery_block_reason()}",
            )
        if self.stop_controller.is_breaker_tripped():
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="CIRCUIT_BREAKER_TRIPPED",
            )
        if self.run_mode == RunMode.READ_ONLY:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="LIVE_READ_ONLY_BLOCK",
            )
        if self.run_mode == RunMode.SIM:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"RUN_MODE_BLOCK:{self.run_mode.value}",
            )
        if self.run_mode not in {RunMode.PAPER, RunMode.LIVE}:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"RUN_MODE_BLOCK:{self.run_mode.value}",
            )
        if self._failsafe_block_new_entries and str(getattr(risk_decision, "direction", "")).upper() in {"BUY", "LONG"}:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="LIFECYCLE_FAILSAFE_BLOCK_NEW_ENTRIES",
            )
        if not self.execution_enabled:
            print("[EXECUTION][BLOCKED] reason=EXECUTION_DISABLED")
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="EXECUTION_DISABLED",
            )
        if not getattr(risk_decision, "decision_id", None):
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=DECISION_ARTIFACT_MISSING,
            )
        if get_ibkr_readonly_enabled() and self.run_mode == RunMode.LIVE:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="BROKER_READONLY_BLOCK",
            )
        if self.run_mode == RunMode.LIVE and not getattr(risk_decision, "allowed", True):
            effective_quantity = self._effective_quantity_from_risk_decision(risk_decision)
            return ExecutionResult(
                symbol=risk_decision.symbol,
                trader_type=risk_decision.trader_type,
                attempted=False,
                status="BLOCKED",
                rationale="Risk engine blocked this trade; no execution attempted.",
                direction=risk_decision.direction,
                quantity=effective_quantity,
                stop_loss_price=risk_decision.stop_loss_price,
                take_profit_price=risk_decision.take_profit_price,
                requested_quantity=effective_quantity,
                filled_quantity=0,
                remaining_quantity=effective_quantity,
            )
        if self.run_mode == RunMode.LIVE and bool(getattr(risk_decision, "validation_override", False)):
            print(
                "[EXECUTION][BLOCK] "
                f"symbol={risk_decision.symbol} reason=VALIDATION_OVERRIDE_LIVE_PROTECTION"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="VALIDATION_OVERRIDE_LIVE_PROTECTION",
            )
        if not provider_ready:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="BROKER_PROVIDER_NOT_READY",
            )
        if not broker_connected:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="BROKER_NOT_CONNECTED",
            )
        requested_quantity = int(getattr(risk_decision, "max_position_size", 0) or 0)
        if requested_quantity <= 0:
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="INVALID_ORDER_QUANTITY",
            )
        duplicate = self.trade_registry.get_trade(
            risk_decision.symbol,
            getattr(risk_decision, "trader_type", "MANUAL"),
        )
        direction = str(getattr(risk_decision, "direction", "")).upper()
        reason_code = str(getattr(risk_decision, "reason_code", "") or "").upper()
        if (
            duplicate is not None
            and direction in {"LONG", "BUY"}
            and reason_code != "TRADE_MANAGEMENT_ADD"
            and (getattr(risk_decision, "relationship_context", None) or {}).get("action") != "ADD"
        ):
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="DUPLICATE_POSITION_CONFLICT",
            )
        return None

    def _autonomous_recovery_preflight_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        authority = getattr(self, "autonomous_recovery_authority", None)
        if authority is None:
            return None
        is_new_entry = self._autonomous_recovery_is_new_entry(risk_decision)
        decision = self._resolve_autonomous_recovery_decision(authority, risk_decision)
        blocks_entry = is_new_entry and decision.blocks_new_entries
        blocks_management = (not is_new_entry) and not decision.allows_existing_position_management
        if blocks_entry or blocks_management:
            print(
                "[AUTONOMOUS_RECOVERY][BLOCKED] "
                f"symbol={risk_decision.symbol} status={decision.recovery_status.value} "
                f"reason={decision.rationale}"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"AUTONOMOUS_RECOVERY_{decision.recovery_status.value}:{decision.rationale}",
            )
        return None

    def _resolve_autonomous_recovery_decision(
        self,
        authority: AutonomousRecoveryAuthority,
        risk_decision: RiskDecision,
    ) -> AutonomousRecoveryDecision:
        current = authority.current_decision()
        if current is not None:
            return current
        return authority.evaluate(
            run_mode=self.run_mode.value,
            broker_connected=True,
            broker_truth_available=True,
            storage_available=True,
            storage_replay_required=False,
            event_replay_complete=True,
            daily_risk_recovered=True,
            lifecycle_recovered=True,
            order_state_known=True,
            audit_payload={
                "source": "ExecutionEngine",
                "symbol": getattr(risk_decision, "symbol", None),
                "strategy_name": getattr(risk_decision, "strategy_name", None),
                "intent_id": getattr(risk_decision, "intent_id", None),
                "risk_decision_id": getattr(risk_decision, "decision_id", None),
                "force_execute": bool(getattr(risk_decision, "force_execute", False)),
            },
            event_collector=self.event_collector,
        )

    @staticmethod
    def _autonomous_recovery_is_new_entry(risk_decision: RiskDecision) -> bool:
        direction = str(getattr(risk_decision, "direction", "") or "").upper()
        reason_code = str(getattr(risk_decision, "reason_code", "") or "").upper()
        if "REPAIR" in reason_code or "EXIT" in reason_code:
            return False
        if direction in {"BUY", "LONG", "SHORT"}:
            return True
        return False

    def _daily_risk_preflight_check(self, risk_decision: RiskDecision) -> Optional[ExecutionResult]:
        if self.daily_risk_governor is None:
            return None
        is_new_entry = self._daily_risk_is_new_entry(risk_decision)
        decision = self.daily_risk_governor.evaluate(
            run_mode=self.run_mode.value,
            recovery_complete=self.startup_recovery_complete(),
            is_new_entry=is_new_entry,
            now=self._daily_risk_evaluation_time(risk_decision),
            event_collector=self.event_collector,
            storage_engine=self._storage_engine,
            trade_lifecycle_engine=self._trade_lifecycle_engine,
            provider=self._provider,
            audit_payload={
                "source": "ExecutionEngine",
                "symbol": getattr(risk_decision, "symbol", None),
                "strategy_name": getattr(risk_decision, "strategy_name", None),
                "intent_id": getattr(risk_decision, "intent_id", None),
                "risk_decision_id": getattr(risk_decision, "decision_id", None),
                "force_execute": bool(getattr(risk_decision, "force_execute", False)),
            },
        )
        blocks_entry = is_new_entry and decision.blocks_new_entries
        blocks_management = (not is_new_entry) and not decision.allows_existing_position_management
        if blocks_entry or blocks_management:
            print(
                "[DAILY_RISK][BLOCKED] "
                f"symbol={risk_decision.symbol} status={decision.status.value} reason={decision.reason}"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale=f"DAILY_RISK_{decision.status.value}:{decision.reason}",
            )
        return None

    def _daily_risk_evaluation_time(self, risk_decision: RiskDecision) -> datetime:
        for candidate in (
            getattr(risk_decision, "timestamp", None),
            getattr(risk_decision, "created_at", None),
            self._latest_event_timestamp(),
        ):
            resolved = self._coerce_daily_risk_datetime(candidate)
            if resolved is not None:
                return resolved
        return datetime.now(timezone.utc)

    def _latest_event_timestamp(self) -> object:
        snapshot_all = getattr(self.event_collector, "snapshot_all", None)
        if not callable(snapshot_all):
            return None
        try:
            events = snapshot_all()
        except Exception:
            return None
        for event in reversed(events):
            timestamp = getattr(event, "timestamp", None)
            if timestamp is not None:
                return timestamp
        return None

    @staticmethod
    def _coerce_daily_risk_datetime(value: object) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            resolved = value
        else:
            try:
                resolved = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if resolved.tzinfo is None:
            return resolved.replace(tzinfo=timezone.utc)
        return resolved
    @staticmethod
    def _daily_risk_is_new_entry(risk_decision: RiskDecision) -> bool:
        direction = str(getattr(risk_decision, "direction", "") or "").upper()
        if direction in {"BUY", "LONG", "SHORT"}:
            return True
        return False

    def _resolve_idempotency_key(self, risk_decision: RiskDecision, tick: int) -> str:
        payload = {
            "symbol": risk_decision.symbol,
            "trader_type": risk_decision.trader_type,
            "strategy_name": risk_decision.strategy_name,
            "direction": risk_decision.direction,
            "requested_quantity": getattr(risk_decision, "max_position_size", 1),
            "stop_loss_price": risk_decision.stop_loss_price,
            "take_profit_price": risk_decision.take_profit_price,
            "tick": tick,
        }
        payload_components = [f"{key}={payload[key]}" for key in sorted(payload)]
        payload_fingerprint = "|".join(payload_components)

        decision_id = getattr(risk_decision, "decision_id", None)
        if decision_id:
            base = f"decision:{decision_id}|{payload_fingerprint}"
        else:
            intent_id = getattr(risk_decision, "intent_id", None)
            if intent_id:
                base = f"intent:{intent_id}|{payload_fingerprint}"
            else:
                base = f"payload:{payload_fingerprint}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    def _is_duplicate(self, idempotency_key: str) -> bool:
        if idempotency_key in self._seen_idempotency_keys:
            return True
        self._seen_idempotency_keys.add(idempotency_key)
        return False

    def _duplicate_result(
        self, risk_decision: RiskDecision, idempotency_key: str
    ) -> ExecutionResult:
        effective_quantity = self._effective_quantity_from_risk_decision(risk_decision)
        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": risk_decision.symbol,
                "trader_type": risk_decision.trader_type,
                "strategy_name": risk_decision.strategy_name,
                "direction": risk_decision.direction,
                "requested_quantity": effective_quantity,
                "run_mode": self.run_mode.value,
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
                "reason": "IDEMPOTENT_DUPLICATE",
                "idempotency_key": idempotency_key,
            },
        )
        return ExecutionResult(
            symbol=risk_decision.symbol,
            trader_type=risk_decision.trader_type,
            attempted=False,
            status="DUPLICATE",
            rationale="Duplicate intent detected; skipping submission.",
            direction=risk_decision.direction,
            quantity=effective_quantity,
            stop_loss_price=risk_decision.stop_loss_price,
            take_profit_price=risk_decision.take_profit_price,
            requested_quantity=effective_quantity,
            filled_quantity=0,
            remaining_quantity=effective_quantity,
            fill_status="NONE",
            note="IDEMPOTENT_DUPLICATE",
            rejection_reason="IDEMPOTENT_DUPLICATE",
            client_order_id=idempotency_key,
        )

    def _order_from_risk_decision(
        self, risk_decision: RiskDecision, tick: int
    ) -> BrokerOrderRequest:
        if getattr(risk_decision, "force_execute", False):
            print(f"[ORDER][FORCED_CREATE] symbol={risk_decision.symbol}")
        self._assert_execution_enabled_for_order_construction("risk decision")
        raw_quantity = int(getattr(risk_decision, "max_position_size", 0) or 0)
        if str(getattr(risk_decision, "strategy_name", "")).upper() == "LIVE_EXECUTION_PROBE":
            raw_quantity = 1
        if raw_quantity <= 0:
            raise RuntimeError("INVALID_INTERNAL_ORDER_QUANTITY")
        requested_quantity = self._clamp_order_quantity(raw_quantity, symbol=risk_decision.symbol)
        print(f"[EXECUTION][SIZE_ACCEPT] symbol={risk_decision.symbol} approved_quantity={requested_quantity}")
        client_order_id = f"{risk_decision.decision_id}-{uuid.uuid4().hex[:8]}"
        context = getattr(risk_decision, "relationship_context", None) or {}
        if context.get("management_action_id"):
            client_order_id = context["management_action_id"]
        print(
            "[ORDER][BUILD] "
            f"symbol={risk_decision.symbol} order_type=MKT qty={requested_quantity} side=BUY"
        )
        request = BrokerOrderRequest(
            client_order_id=client_order_id,
            symbol=risk_decision.symbol,
            direction=risk_decision.direction,
            quantity=requested_quantity,
            order_type="MKT",
            trader_type=risk_decision.trader_type,
            strategy_name=risk_decision.strategy_name,
            attempt_number=1,
            created_tick=tick,
            stop_loss_price=risk_decision.stop_loss_price,
            take_profit_price=risk_decision.take_profit_price,
            pattern_name=getattr(risk_decision, "pattern_name", None),
            invalidation_level=getattr(risk_decision, "invalidation_level", None),
            next_retry_tick=None,
            setup_family_id=getattr(risk_decision, "setup_family_id", None),
            trigger_id=getattr(risk_decision, "trigger_id", None),
            target_model=getattr(risk_decision, "target_model", None),
            relationship_context=getattr(risk_decision, "relationship_context", None),
            setup_metadata=getattr(risk_decision, "setup_metadata", None),
            management_session_plan=getattr(risk_decision, "management_session_plan", None),
        )
        self._prospective_decisions_by_order_id.clear()  # One execution-thread construction/handoff slot.
        self._prospective_decisions_by_order_id[client_order_id] = risk_decision.decision_id
        capital_decision = getattr(risk_decision, "capital_decision", None)
        if isinstance(capital_decision, CapitalDecision):
            self._capital_decisions_by_order_id[client_order_id] = capital_decision.decision_id
            self.capital_authority.attach_order(
                decision_id=capital_decision.decision_id,
                order_id=client_order_id,
            )
        strategy_allocation_decision = getattr(risk_decision, "strategy_allocation_decision", None)
        if isinstance(strategy_allocation_decision, StrategyAllocationDecision):
            self._strategy_allocation_decisions_by_order_id[client_order_id] = (
                strategy_allocation_decision.decision_id
            )
            self.strategy_allocation_authority.attach_order(
                decision_id=strategy_allocation_decision.decision_id,
                order_id=client_order_id,
                global_capital_decision_id=getattr(risk_decision, "capital_decision_id", None),
            )
        return request

    @staticmethod
    def route_order(request: BrokerOrderRequest) -> str:
        # future: select best venue
        return "IBKR_SMART"

    @staticmethod
    def submission_confirmed(result: ExecutionResult) -> bool:
        """Accepted native result with retained callback acknowledgement evidence."""
        return ExecutionResult.submission_confirmed(result)

    def _route_order(self, request: BrokerOrderRequest) -> ExecutionResult:
        readonly = get_ibkr_readonly_enabled()
        submission_enabled = bool(get_config("IBKR_ORDER_SUBMISSION_ENABLED"))
        print("[EXECUTION][GATE]", f"execution_enabled={self.execution_enabled}", f"readonly={readonly}", f"submission_enabled={submission_enabled}")
        if not self.execution_enabled:
            print("[EXECUTION][BLOCKED] reason=EXECUTION_DISABLED")
            self._release_strategy_allocation_for_order(request, reason="EXECUTION_DISABLED")
            self._release_capital_for_order(request, reason="EXECUTION_DISABLED")
            return self._blocked_execution_from_request(request)
        if self._provider is None:
            raise RuntimeError("ExecutionEngine execution provider missing for execution path.")
        if self.run_mode == RunMode.LIVE and str(request.strategy_name or "").upper() == "LIVE_EXECUTION_PROBE" and str(request.direction).upper() == "LONG":
            print(f"[PROBE][BUY] symbol={request.symbol} qty={request.quantity}")
            self._require_exit_stage.add(request.client_order_id)
        if str(request.direction).upper() == "SELL" and self._get_open_trades_for_symbol(request.symbol):
            print(f"[EXECUTION][CLOSE] symbol={request.symbol} qty={request.quantity}")
            print(f"[EXIT][SUBMIT] symbol={request.symbol} qty={request.quantity} order_id={request.client_order_id}")
        print("[ORDER_SUBMIT]", f"symbol={request.symbol}", f"side={request.direction}", f"qty={request.quantity}")
        print(
            f"[IBKR][ORDER_SUBMIT] order_id={request.client_order_id} symbol={request.symbol} "
            f"side={request.direction} qty={request.quantity} mode={self.run_mode.value}"
        )
        self._record_order_stage(request.client_order_id, "SUBMIT")
        self._execution_log(
            "SUBMIT",
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            run_mode=self.run_mode.value,
            side=request.direction,
            qty=request.quantity,
            order_type=request.order_type,
            broker_order_id=request.client_order_id,
        )
        print(
            f"[ORDER][SUBMIT] order_id={request.client_order_id} symbol={request.symbol} "
            f"side={request.direction} qty={request.quantity} order_type={request.order_type}"
        )
        print(
            "[EXECUTION][AUDIT] "
            f"symbol={request.symbol} "
            f"side={request.direction} "
            f"size={request.quantity} "
            f"session={getattr(request, 'session', 'UNKNOWN')} "
            f"strategy={request.strategy_name or 'UNKNOWN'} "
            f"pattern={request.pattern_name or 'UNKNOWN'} "
            f"capital={request.quantity} "
            f"ibkr_order_id={request.client_order_id} "
            f"route={self.route_order(request)}"
        )
        print(
            f"[ORDER_ROUTE_ATTEMPT] symbol={request.symbol} qty={request.quantity} type={request.order_type}"
        )
        context = request.relationship_context or {}
        if context and context.get("action") in {"ENTRY", "REENTRY", "ADD"}:
            manager = getattr(self, "relationship_manager", None)
            if manager is None or not manager.register_relationship_order(
                relationship_id=context["relationship_id"], symbol=request.symbol,
                security_id=context["security_id"], parent_id=context["parent_id"], child_id=context["child_id"],
                order_id=request.client_order_id, quantity=request.quantity, stop=request.stop_loss_price,
                action=context["action"]):
                return ExecutionResult(symbol=request.symbol, trader_type=request.trader_type or "UNKNOWN",
                    attempted=False, status="BLOCKED", rationale="RELATIONSHIP_RESERVATION_BLOCK")
        if context:
            from dataclasses import asdict
            manager = getattr(self, "relationship_manager", None)
            plan = manager._relationship_plans.get(context.get("relationship_id")) if manager else None
            if (plan is None or request.client_order_id not in plan.orders
                    or plan.orders[request.client_order_id]["terminal"] or plan.pending_stop_resize):
                return ExecutionResult(symbol=request.symbol, trader_type=request.trader_type or "UNKNOWN",
                    attempted=False, status="BLOCKED", rationale="RELATIONSHIP_ORDER_NOT_RESERVED")
            plan.orders[request.client_order_id]["request"] = asdict(request)
            # Only newly dispatched native owned requests enter prospective evidence.
            decisions = getattr(self, "_prospective_decisions_by_order_id", {})
            owned = plan.orders[request.client_order_id]
            version = owned.get("owner_effect_version")
            if version is not None and (type(version) is not int or version != 1):
                raise ValueError("OWNER_EFFECT_VERSION_INVALID")
            decision_id = decisions.get(request.client_order_id)
            if owned.get("owner_effect_version") == 1:
                decision_id = owned.get("decision_id")
            native_owned = self.run_mode in {RunMode.PAPER, RunMode.LIVE} and self._provider.is_live()
            if native_owned:
                if not decision_id:
                    raise RuntimeError("OWNER_EFFECT_DECISION_ID_UNAVAILABLE")
                owned["owner_effect_version"] = 1
                owned["decision_id"] = decision_id
            manager._save_relationship_state()
            if native_owned:
                self._storage_engine.validate_owner_effect_storage()
            decisions.pop(request.client_order_id, None)
        standalone = None
        if (not context and self.run_mode == RunMode.PAPER and self._provider.is_live()
                and request.direction.upper() in {"LONG", "BUY"}):
            standalone = self._retain_native_request(request)
        try:
            result = self._provider.place_order(request)
        except Exception as exc:
            if context:
                plan.orders[request.client_order_id]["submission_uncertain_at"] = datetime.now(timezone.utc).isoformat()
                manager._save_relationship_state()
            elif standalone is not None:
                self._failsafe_block_new_entries = True
            else:
                self._release_strategy_allocation_for_order(request, reason="ENTRY_SUBMISSION_FAILURE")
                self._release_capital_for_order(request, reason="ENTRY_SUBMISSION_FAILURE")
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="SUBMISSION_UNKNOWN" if context or standalone is not None else "FAILED",
                relationship_context=request.relationship_context,
                rationale=f"ENTRY_SUBMISSION_FAILURE:{exc}",
                direction=request.direction,
                quantity=request.quantity,
                stop_loss_price=request.stop_loss_price,
                take_profit_price=request.take_profit_price,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="ENTRY_SUBMISSION_FAILURE",
                rejection_reason="ENTRY_SUBMISSION_FAILURE",
                attempt_number=request.attempt_number,
                client_order_id=request.client_order_id,
            )
        if standalone is not None:
            native = getattr(result, "ibkr_order_id", None)
            if native is not None:
                if isinstance(native, bool) or not str(native).isdigit() or int(native) <= 0:
                    self._native_quarantined = True
                    raise ValueError("NATIVE_ORDER_ID_INVALID")
                native = str(native)
                if any(o is not standalone and o.get("broker_order_id") == native for o in self._native_orders.values()):
                    self._native_quarantined = True
                    raise ValueError("NATIVE_ORDER_ID_CONFLICT")
                standalone["broker_order_id"] = native
            if not standalone.get("broker_order_id"):
                self._failsafe_block_new_entries = True
            standalone["last_response"] = {"status": str(result.status), "filled": result.filled_quantity, "remaining": result.remaining_quantity}
            self._save_native_orders()  # Failure retains pre-dispatch uncertainty.
        from src.brokers.sim_broker import SimBroker
        deterministic_result = (isinstance(self._provider, PaperExecutionProvider)
            and isinstance(self._provider.broker, SimBroker)
            and str(result.status).upper() in {"SIMULATED", "NOT_FILLED", "EXPIRED", "REJECTED", "BLOCKED", "FAILED", "RETRY_SCHEDULED"})
        if context and not deterministic_result and not getattr(result, "ibkr_order_id", None) and str(result.status).upper() in {"FAILED", "BLOCKED", "EXPIRED", "RETRY_SCHEDULED"}:
            order = plan.orders[request.client_order_id]
            order["submission_uncertain_at"] = datetime.now(timezone.utc).isoformat()
            order["provider_status"] = result.status
            manager._save_relationship_state()
            result.status = "SUBMISSION_UNKNOWN"
            self._record_fill_and_position(request, result)
            return result
        self._execution_log(
            "SUBMIT_RESULT",
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            run_mode=self.run_mode.value,
            side=request.direction,
            qty=request.quantity,
            broker_order_id=getattr(result, "client_order_id", None) or request.client_order_id,
            status=getattr(result, "status", None),
            reason=getattr(result, "rejection_reason", None) or getattr(result, "rationale", None),
        )
        print(
            "[EXECUTION][SUBMIT_RESULT] "
            f"symbol={request.symbol} order_id={getattr(result, 'ibkr_order_id', None)} "
            f"status={getattr(result, 'status', None)}"
        )
        result = self._confirm_broker_ack(request, result)
        if context and str(result.status).upper() == "SUBMISSION_UNKNOWN":
            order = plan.orders[request.client_order_id]
            order["submission_uncertain_at"] = datetime.now(timezone.utc).isoformat()
            manager._save_relationship_state()
        if self.submission_confirmed(result):
            print(f"[ORDER_SUBMITTED] symbol={request.symbol} qty={request.quantity} type={request.order_type}")
            print(f"[EXECUTION] SUBMITTED symbol={request.symbol} qty={request.quantity} "
                  f"order_id={result.ibkr_order_id}")
            if str(request.direction).upper() == "SELL":
                print(f"[EXIT][SUBMIT] symbol={request.symbol} qty={request.quantity} "
                      f"broker_order_id={result.ibkr_order_id}")
        self._log_ibkr_status(request, result)
        if standalone is None:
            self._record_fill_and_position(request, result)
        self._run_live_probe_exit_if_needed(request, result)
        self._validate_trace_integrity(request.client_order_id)
        if not self._provider.is_live():
            print(
                f"[EXECUTION] {self.run_mode.value} mode active — "
                f"provider={self._provider.name()} deterministic flow."
            )
        else:
            print("[EXECUTION] LIVE broker order routed.")
        retry_enqueued = self._schedule_retry(request, result)
        if context and deterministic_result and not retry_enqueued:
            result.relationship_context = {**context, "deterministic_attempt_terminal": True}
        self._release_capital_for_terminal_result(
            request,
            result,
            retry_enqueued=retry_enqueued,
        )
        self._release_strategy_allocation_for_terminal_result(
            request,
            result,
            retry_enqueued=retry_enqueued,
        )
        self._run_protection_reconciliation(reason="post_order_route")
        return result

    def _validate_required_order_fields(
        self, risk_decision: RiskDecision, request: BrokerOrderRequest
    ) -> Optional[ExecutionResult]:
        entry_price = getattr(risk_decision, "entry_price", None)
        quantity = getattr(request, "quantity", None)
        side = getattr(request, "direction", None)
        if entry_price is None or quantity is None or side is None:
            print(
                "[EXECUTION][BLOCK] "
                f"symbol={request.symbol} reason=invalid_order_fields "
                f"entry_price={entry_price} quantity={quantity} side={side}"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="invalid_order_fields",
            )
        stop_loss_price = getattr(request, "stop_loss_price", None)
        side_upper = str(side).upper()
        if self.run_mode in {RunMode.PAPER, RunMode.LIVE} and side_upper in {"LONG", "BUY"} and stop_loss_price is None:
            print(
                "[EXECUTION][BLOCK] "
                f"symbol={request.symbol} trader_type={request.trader_type} reason=missing_stop_loss_price"
            )
            return self._blocked_execution_from_risk_decision(
                risk_decision,
                rationale="MISSING_STOP_LOSS_PRICE",
            )
        if self.run_mode in {RunMode.PAPER, RunMode.LIVE} and side_upper in {"LONG", "BUY"} and stop_loss_price is not None:
            try:
                validate_stop_price(
                    side=side_upper,
                    stop_price=float(stop_loss_price),
                    entry_price=float(entry_price),
                )
            except StopAuthorityError as exc:
                print(
                    "[EXECUTION][BLOCK] "
                    f"symbol={request.symbol} trader_type={request.trader_type} reason={exc.reason_code}"
                )
                return self._blocked_execution_from_risk_decision(
                    risk_decision,
                    rationale=exc.reason_code,
                )
        return None

    def _confirm_broker_ack(
        self, request: BrokerOrderRequest, result: ExecutionResult
    ) -> ExecutionResult:
        if not self._provider.is_live():
            return result
        ibkr_order_id = getattr(result, "ibkr_order_id", None)
        status_raw = str(getattr(result, "status", "") or "")
        status_upper = status_raw.upper()
        if status_upper in {"REJECTED", "CANCELLED", "CANCELED", "INACTIVE"}:
            # Definitive terminal status needs no positive submission ack;
            # preserve relationship identity for terminal result processing.
            return result
        if ibkr_order_id is None or status_raw not in self.VALID_IBKR_STATUSES:
            # Missing/unsupported acknowledgement evidence is not a terminal
            # broker rejection. Keep identity and exposure until reconciliation.
            self.execution_integrity_flag = True
            result.status = "SUBMISSION_UNKNOWN"
            return result

        broker_status = "Submitted"
        if status_upper in {"FILLED"} or getattr(result, "filled_quantity", 0) > 0:
            broker_status = "Filled"
        print(
            f"[IBKR][ORDER_ACK] order_id={ibkr_order_id} status={broker_status} "
            f"symbol={request.symbol}"
        )
        print(f"[ORDER][ACK] order_id={ibkr_order_id} status={broker_status}")
        print(f"[EXECUTION][ORDER_TRACK] order_id={ibkr_order_id} status={broker_status}")
        self._execution_log(
            "ORDER_STATUS",
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            run_mode=self.run_mode.value,
            side=request.direction,
            qty=request.quantity,
            broker_order_id=ibkr_order_id,
            status=broker_status,
        )
        self._record_order_stage(request.client_order_id, "ACK")
        return result

    def _owner_effect_binding(self, request, result, owner: str, effect: str, delta: int, price: float) -> dict | None:
        manager = getattr(self, "relationship_manager", None)
        context = request.relationship_context or {}
        plan = manager._relationship_plans.get(context.get("relationship_id")) if manager else None
        owned = plan.orders.get(request.client_order_id) if plan else None
        if not owned or owned.get("owner_effect_version") is None:
            return None
        if type(owned.get("owner_effect_version")) is not int or owned["owner_effect_version"] != 1:
            raise ValueError("OWNER_EFFECT_VERSION_INVALID")
        binding = {"version": 1, "mode": self.run_mode.value, "security_id": plan.security_id,
            "symbol": plan.symbol, "relationship_id": plan.relationship_id, "decision_id": owned.get("decision_id"),
            "order_id": request.client_order_id, "native_order_id": str(owned.get("broker_order_id") or ""),
            "owner": owner, "effect": effect, "cumulative_quantity": int(result.filled_quantity),
            "delta_quantity": delta, "average_price": float(result.average_fill_price or result.entry_price or 0), "delta_price": price}
        self._storage_engine._owner_effect_record(binding, phase="PREPARED")
        return binding

    def _record_fill_and_position(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        # The broker callback carries fill facts; protection belongs to the
        # risk-approved request and must survive into recurring management.
        result.stop_loss_price = request.stop_loss_price
        result.take_profit_price = request.take_profit_price
        result.strategy_name = request.strategy_name
        result.setup_family_id = request.setup_family_id
        result.trigger_id = request.trigger_id
        result.target_model = request.target_model
        result.relationship_context = request.relationship_context
        result.client_order_id = request.client_order_id
        context = request.relationship_context or {}
        manager = getattr(self, "relationship_manager", None)
        plan = manager._relationship_plans.get(context.get("relationship_id")) if manager else None
        stored_order = plan.orders.get(request.client_order_id) if plan else None
        if stored_order is not None and getattr(result, "ibkr_order_id", None) is not None:
            if (stored_order.get("owner_effect_version") is not None and stored_order.get("broker_order_id")
                    and str(stored_order["broker_order_id"]) != str(result.ibkr_order_id)):
                raise ValueError("OWNER_EFFECT_NATIVE_ID_CONFLICT")
            stored_order["broker_order_id"] = str(result.ibkr_order_id)
            manager._save_relationship_state()
        filled_quantity = int(getattr(result, "filled_quantity", 0) or 0)
        if filled_quantity <= 0:
            return
        cumulative_quantity = filled_quantity
        previous = self.position_records.get(request.client_order_id, {})
        if not previous and stored_order is not None and stored_order["filled"]:
            previous = {"filled_qty": stored_order["filled"], "entry_price": stored_order["notional"] / stored_order["filled"]}

        native_owned = self._native_orders.get(request.client_order_id)
        native_parent, native_life = self._native_protection_owner(native_owned) if native_owned is not None else (None, None)
        if request.relationship_context or native_owned is not None:
            filled_quantity -= int(previous.get("filled_qty", 0))
            if filled_quantity <= 0:
                return
        remaining_quantity = int(getattr(result, "remaining_quantity", 0) or 0)
        fill_track_status = "PARTIAL_FILL" if remaining_quantity > 0 else "Filled"
        ibkr_order_id = getattr(result, "ibkr_order_id", None)
        if ibkr_order_id is not None:
            print(
                "[EXECUTION][ORDER_TRACK] "
                f"order_id={ibkr_order_id} status={fill_track_status} "
                f"filled={filled_quantity} remaining={remaining_quantity}"
            )
        entry_price = getattr(result, "entry_price", None) or getattr(result, "average_fill_price", None)
        direction_upper = str(request.direction).upper()
        fill_price = self._float_or_none(entry_price) or 0.0
        cumulative_price = fill_price
        if (request.relationship_context or native_owned is not None) and int(previous.get("filled_qty", 0)):
            fill_price = (cumulative_quantity * fill_price - int(previous["filled_qty"]) * float(previous["entry_price"])) / filled_quantity
        prospective = bool(stored_order and stored_order.get("owner_effect_version") is not None)
        pending = {"cumulative_quantity": cumulative_quantity, "average_price": float(entry_price or 0), "version": 1}
        if prospective:
            stored_order["owner_effect_pending"] = pending
            manager._save_relationship_state()
        try:
            if direction_upper in {"LONG", "BUY", "SHORT"}:
                self._convert_strategy_allocation_for_fill(request, filled_quantity=filled_quantity, fill_price=fill_price,
                    **({"effect_evidence": self._owner_effect_binding(request, result, "allocation", "CONVERT", filled_quantity, fill_price)} if prospective else {}))
                self._convert_capital_for_fill(request, filled_quantity=filled_quantity, fill_price=fill_price,
                    **({"effect_evidence": self._owner_effect_binding(request, result, "capital", "CONVERT", filled_quantity, fill_price)} if prospective else {}))
            elif direction_upper == "SELL":
                entry_request = plan.orders.get(plan.initial_order_id, {}).get("request", {}) if plan else (native_parent["request"] if native_parent else {})
                owner_strategy = entry_request.get("strategy_name") or request.strategy_name
                release_price = fill_price
                if plan is not None or native_parent is not None:
                    lifecycle = (self.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
                        if plan else native_life)
                    position = manager.snapshot_positions().get(request.symbol)
                    # Exposure is entry cost, not exit proceeds; PnL retains fill_price.
                    release_price = float(lifecycle.avg_fill_price if lifecycle is not None
                                          else position.entry_price if position is not None else 0.0)
                self.strategy_allocation_authority.release_exposure(
                    strategy_id=owner_strategy or "UNKNOWN",
                    quantity=filled_quantity,
                    price=release_price,
                    reason="EXIT_FILL",
                    **({"effect_evidence": self._owner_effect_binding(request, result, "allocation", "RELEASE", filled_quantity, release_price)} if prospective else {}),
                )
                self.capital_authority.release_exposure(
                    symbol=request.symbol,
                    quantity=filled_quantity,
                    price=release_price,
                    strategy_id=owner_strategy,
                    reason="EXIT_FILL",
                    **({"effect_evidence": self._owner_effect_binding(request, result, "capital", "RELEASE", filled_quantity, release_price)} if prospective else {}),
                )
            if prospective:
                stored_order.pop("owner_effect_pending")
                manager._save_relationship_state()
        except BaseException:
            if prospective:
                stored_order["owner_effect_pending"] = pending
                plan.paused = True
                self._mark_capital_recovery_failed("OWNER_EFFECT_EVIDENCE_RECOVERY_REQUIRED")
                # Existing last durable pending record survives even if saving
                # the additional in-memory pause is itself unavailable.
            raise
        print(
            f"[ORDER][FILL] order_id={request.client_order_id} "
            f"symbol={request.symbol} qty={filled_quantity} entry_price={entry_price}"
        )
        self._execution_log(
            "FILL",
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            run_mode=self.run_mode.value,
            side=request.direction,
            qty=filled_quantity,
            entry_price=entry_price,
            broker_order_id=request.client_order_id,
            status=getattr(result, "status", None),
        )
        self._record_order_stage(request.client_order_id, "FILL")
        self.position_records[request.client_order_id] = {
            "trade_id": request.client_order_id,
            "symbol": str(request.symbol).upper(),
            "direction": str(request.direction).upper(),
            "order_type": request.order_type,
            "strategy_name": request.strategy_name,
            "filled_qty": cumulative_quantity,
            "remaining_qty": remaining_quantity,
            "entry_price": cumulative_price,
            "timestamp": time.time(),
        }
        context = request.relationship_context or {}
        manager = getattr(self, "relationship_manager", None)
        plan = manager._relationship_plans.get(context.get("relationship_id")) if manager else None
        protection_id = (plan.protection_trade_id or plan.initial_order_id) if plan else (native_life.trade_id if native_life else request.client_order_id)
        existing_protection = self.post_fill_lifecycle.get_trade(protection_id) if plan or native_owned is not None else None
        if direction_upper in {"LONG", "BUY"} and existing_protection is not None:
            total = existing_protection.filled_qty + filled_quantity
            average = (existing_protection.filled_qty * existing_protection.avg_fill_price + filled_quantity * fill_price) / total
            if plan is not None:
                plan.pending_stop_resize = plan.pending_stop_resize or self.run_mode in {RunMode.PAPER, RunMode.LIVE}
                manager._save_relationship_state()  # dispatch is not quantity confirmation
            protection_result = self.post_fill_lifecycle.update_selected_exposure(
                trade_id=protection_id, filled_qty=total, avg_fill_price=average)
            protection_id = protection_result.get("reopened_trade_id", protection_id)
            if not protection_result["success"]:
                if plan is not None:
                    plan.pending_stop_resize = True
                    manager._save_relationship_state()
            self._failsafe_block_new_entries = self._failsafe_block_new_entries or bool(plan and plan.pending_stop_resize) or not protection_result["success"]
            self.position_records[request.client_order_id]["lifecycle"] = protection_result
        elif direction_upper in {"LONG", "BUY"}:
            protection_result = self.post_fill_lifecycle.activate_trade_management_after_fill(
                trade_id=protection_id,
                symbol=request.symbol,
                side=request.direction,
                filled_qty=filled_quantity,
                avg_fill_price=float(entry_price or 0.0),
                strategy_id=request.strategy_name or "UNKNOWN",
                intended_qty=request.quantity,
                session_label=self.run_mode.value,
                stop_loss_price=request.stop_loss_price,
                take_profit_price=request.take_profit_price,
                preserve_selected_protection="ROSS" in str(request.strategy_name or "").upper(),
                target_model=request.target_model,
                entry_broker_order_id=str(ibkr_order_id) if ibkr_order_id is not None else None,
            )
            self.position_records[request.client_order_id]["lifecycle"] = protection_result
            if (plan is not None or native_owned is not None) and not protection_result["success"]:
                self._failsafe_block_new_entries = True
        if direction_upper == "SELL" and native_parent is not None:
            applied = self.post_fill_lifecycle.record_exit_fill(trade_id=protection_id, fill_price=fill_price,
                fill_time=datetime.now(timezone.utc).isoformat(), actual_qty=filled_quantity,
                exit_order_id=str(ibkr_order_id), reason=((native_parent["pmh_failure_exit"]["profile"].removesuffix("_V1"))
                    if (native_parent.get("pmh_failure_exit") or {}).get("status") == "MKT"
                    else ("OWNED_CLOSE_AFTER_PMH_REQUEST" if native_parent["request"].get("setup_family_id") == "PREMARKET_HIGH_BREAK"
                        else "OWNED_CLOSE_AFTER_FAILURE_REQUEST") if native_parent.get("pmh_failure_exit") else "STOP_LOSS"))
            if not applied.get("success"):
                native_owned["lifecycle_application_rejected"] = applied
                raise RuntimeError("NATIVE_PROTECTION_EXIT_APPLICATION_REJECTED")
            existing_protection.stop.status = str(result.status)
        if direction_upper == "SELL" and plan is not None and existing_protection is not None:
            exit_application = self.post_fill_lifecycle.record_exit_fill(trade_id=protection_id, fill_price=fill_price,
                fill_time=datetime.now(timezone.utc).isoformat(), actual_qty=filled_quantity,
                exit_order_id=request.client_order_id,
                reason="STOP_LOSS" if context.get("protective_stop_fill") else "relationship_reduction")
            if not exit_application.get("success"):
                # Retain authoritative per-order facts and the existing recovery
                # latch; no invented short projection, rollback or automatic replay.
                stored_order["lifecycle_application_rejected"] = {
                    "error": exit_application.get("error", "UNKNOWN"),
                    "cumulative_quantity": cumulative_quantity, "average_price": float(entry_price or 0),
                }
                plan.paused = True
                plan.reconciled = False
                manager._save_relationship_state()
                self._mark_capital_recovery_failed("RELATIONSHIP_EXIT_APPLICATION_REJECTED")
            if context.get("protective_stop_fill"):
                # This stop is already executing; do not resize/cancel its own fill.
                existing_protection.stop.status = str(result.status)
                if existing_protection.filled_qty == 0:
                    plan.pending_stop_resize = False
            elif existing_protection.filled_qty > 0:
                plan.pending_stop_resize = plan.pending_stop_resize or self.run_mode in {RunMode.PAPER, RunMode.LIVE}
                manager._save_relationship_state()
                resized = self.post_fill_lifecycle.update_selected_exposure(trade_id=protection_id,
                    filled_qty=existing_protection.filled_qty, avg_fill_price=existing_protection.avg_fill_price)
                if not resized["success"]:
                    plan.pending_stop_resize = True
                    manager._save_relationship_state()
                self._failsafe_block_new_entries = self._failsafe_block_new_entries or plan.pending_stop_resize or not resized["success"]
            elif existing_protection.stop and existing_protection.stop.broker_order_id and self._provider is not None:
                plan.pending_stop_resize = False
                plan.pending_stop_cancel = str(existing_protection.stop.broker_order_id)
                manager._save_relationship_state()
                try:
                    cancelled = self._provider.cancel_order(broker_order_id=plan.pending_stop_cancel)
                    existing_protection.stop.status = str(cancelled.get("status") or "UNKNOWN")
                except Exception:
                    existing_protection.stop.status = "CANCEL_UNCONFIRMED"
                    existing_protection.failure_flags.append("STOP_CANCEL_UNCONFIRMED")
                    self._failsafe_block_new_entries = True
                # Cleanup failure must never discard a confirmed exit fill.


        if plan is not None or native_owned is not None:
            # One registry projection from confirmed aggregate protection. Broker
            # adapters deliberately do not independently register these fills.
            from src.core.active_trade_registry import ActiveTrade
            protected = self.post_fill_lifecycle.get_trade(protection_id)
            if plan is not None and protected is not None and protected.stop is not None:
                plan.protection_trade_id = protection_id
                plan.protection_broker_order_id = str(protected.stop.broker_order_id or "") or None
                manager._save_relationship_state()
            initial_request = plan.orders[plan.initial_order_id].get("request", {}) if plan else (native_parent["request"] if native_parent else asdict(request))
            trader_type = initial_request.get("trader_type") or request.trader_type or "UNKNOWN"
            registered = self.trade_registry.get_trade(request.symbol, trader_type)
            if registered is None:
                candidates = [t for t in self.trade_registry.snapshot() if t.symbol == request.symbol
                              and ("ROSS" in t.strategy_name.upper() or t.strategy_name == "RECOVERY")]
                if len(candidates) == 1:
                    registered = candidates[0]
                    trader_type = registered.trader_type
                elif candidates:
                    self._failsafe_block_new_entries = True
                    if plan is not None:
                        plan.paused = True
                        manager._save_relationship_state()
                    else:
                        self._native_quarantined = True
                    return
            if protected is not None and protected.filled_qty > 0:
                if registered is None:
                    self.trade_registry.register_trade(ActiveTrade(symbol=request.symbol, trader_type=trader_type,
                        entry_tick=request.created_tick or 0, entry_price=protected.avg_fill_price,
                        direction="LONG", quantity=protected.filled_qty, strategy_name=protected.strategy_id,
                        stop_loss_price=protected.stop.trigger_price if protected.stop else request.stop_loss_price))
                else:
                    registered.quantity = protected.filled_qty
                    registered.entry_price = protected.avg_fill_price
                    registered.take_profit_price = None
            elif registered is not None:
                self.trade_registry.unregister_trade(request.symbol, trader_type)

        if direction_upper in {"SHORT", "SELL"}:
            print(
                f"[ORDER][EXIT] order_id={request.client_order_id} symbol={request.symbol} qty={filled_quantity}"
            )
            print(
                f"[EXIT][FILL] symbol={request.symbol} qty={filled_quantity} "
                f"order_id={request.client_order_id}"
            )
            if remaining_quantity <= 0:
                print(
                    f"[EXIT][COMPLETE] symbol={request.symbol} qty={filled_quantity} "
                    f"order_id={request.client_order_id}"
                )
            self._record_order_stage(request.client_order_id, "EXIT")

    def _retain_relationship_stop_fill(self, plan, reader) -> None:
        """Project known protection callbacks into the existing cumulative fill route."""
        broker_id = plan.protection_broker_order_id
        if not broker_id:
            return
        facts = reader(broker_id)
        if not facts:
            return
        order_id = f"{plan.relationship_id}:stop:{broker_id}"
        lifecycle = self.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
        stop = lifecycle.stop if lifecycle is not None else None
        retained = plan.orders.get(order_id, {})
        bound = max(int(retained.get("requested", 0)),
                    int(stop.quantity) if stop and str(stop.broker_order_id) == str(broker_id) else 0)
        try:
            quantities = (facts["filled"], facts["remaining"])
            if any(isinstance(value, bool) or not math.isfinite(float(value))
                   or float(value) != int(value) for value in quantities):
                raise ValueError
            filled, remaining = (int(value) for value in quantities)
            if filled < 0 or remaining < 0 or bound <= 0 or filled + remaining > bound:
                raise ValueError
            if filled == 0:
                return
            if (isinstance(facts.get("avgFillPrice"), bool)
                    or str(facts.get("status") or "").upper() not in self.VALID_CACHED_IBKR_STATUSES):
                raise ValueError
            price = self._float_or_none(facts.get("avgFillPrice"))
            if price is None or not math.isfinite(price) or price <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("CACHED_PROTECTION_UPDATE_INVALID") from None
        original = plan.orders[plan.initial_order_id]
        version = original.get("owner_effect_version")
        if version is not None and (type(version) is not int or version != 1):
            raise ValueError("OWNER_EFFECT_VERSION_INVALID")
        if order_id not in plan.orders:
            from dataclasses import asdict
            initial = plan.orders[plan.initial_order_id].get("request", {})
            context = {"relationship_id": plan.relationship_id, "action": "EXIT", "protective_stop_fill": True}
            request = BrokerOrderRequest(client_order_id=order_id, symbol=plan.symbol, direction="SELL",
                quantity=bound, order_type="STP", trader_type=initial.get("trader_type"),
                strategy_name=initial.get("strategy_name"), relationship_context=context)
            plan.orders[order_id] = {"action": "EXIT", "requested": bound,
                "filled": 0, "notional": 0.0, "terminal": False,
                "broker_order_id": str(broker_id), "request": asdict(request)}
            original = plan.orders[plan.initial_order_id]
            if original.get("owner_effect_version") == 1:
                plan.orders[order_id]["owner_effect_version"] = 1
                plan.orders[order_id]["decision_id"] = original.get("decision_id")
        else:
            # A still-working stop may have been resized for confirmed additions.
            order = plan.orders[order_id]
            order["requested"] = max(order["requested"], filled + remaining)
        self.relationship_manager._save_relationship_state()

    def _consume_cached_order(self, plan, order_id, order, facts, result_processor):
        manager = getattr(self, "relationship_manager", None)
        save = manager._save_relationship_state if plan is not None else self._save_native_orders
        # Validate cumulative native evidence before any accounting or
        # protection side effects. Do not truncate fractional quantities
        # or turn a missing/invalid average price into a zero-price fill.
        try:
            quantities = (facts["filled"], facts["remaining"])
            if any(isinstance(value, bool) or not math.isfinite(float(value))
                   or float(value) != int(value) for value in quantities):
                raise ValueError
            total, remaining = (int(value) for value in quantities)
            previous = self.position_records.get(order_id, {})
            prior = max(int(order["filled"]), int(previous.get("filled_qty", 0)))
            status = str(facts.get("status") or "").upper()
            terminal_statuses = {"FILLED", "REJECTED", "CANCELLED", "CANCELED", "INACTIVE"}
            if (total < 0 or remaining < 0 or total + remaining > order["requested"]
                    or status not in self.VALID_CACHED_IBKR_STATUSES
                    or (plan is None and status == "FILLED" and (remaining != 0 or total != order["requested"]))):
                raise ValueError
            if order["terminal"] and status not in terminal_statuses and total <= order["filled"]:
                return None  # Existing terminal truth cannot regress on a late nonterminal snapshot.
            if total < prior or (plan is None and not order.get("protection_parent_order_id") and order["terminal"] and total > prior):
                raise ValueError
            if plan is None and prior and total == prior and facts.get("avgFillPrice") is not None and float(facts["avgFillPrice"]) != float(previous["entry_price"]):
                raise ValueError
            if total > prior:
                if isinstance(facts["avgFillPrice"], bool):
                    raise ValueError
                average = float(facts["avgFillPrice"])
                old_notional = (prior * float(previous["entry_price"]) if previous
                                else float(order["notional"]))
                delta_price = (total * average - old_notional) / (total - prior)
                if not math.isfinite(average) or average <= 0 or not math.isfinite(delta_price) or delta_price <= 0:
                    raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("CACHED_EXECUTION_UPDATE_INVALID") from None
        if total == order["filled"] and status == order.get("status"):
            if order.get("protection_parent_order_id"):
                _, life = self._native_protection_owner(order)
                self._verify_native_remaining_stop(order, life, total)
            return None
        request = BrokerOrderRequest(**order["request"])
        context = request.relationship_context or {}
        if (request.client_order_id != order_id or request.symbol.upper() != (plan.symbol.upper() if plan else order["symbol"])
                or (plan is not None and context.get("relationship_id") != plan.relationship_id)
                or (plan is None and context)):
            raise ValueError("CACHED_EXECUTION_UPDATE_BINDING_INVALID")
        native_parent, native_life = self._native_protection_owner(order) if plan is None else (None, None)
        if native_parent is not None and total > prior:
            position = manager.snapshot_positions().get(request.symbol) if manager else None
            registered = self.trade_registry.get_trade(request.symbol, native_parent["request"].get("trader_type") or "UNKNOWN")
            if (position is None or position.relationship_id or position.reference_order_id != order["protection_parent_order_id"]
                    or registered is None or position.quantity != native_life.filled_qty or registered.quantity != native_life.filled_qty
                    or position.strategy_name != native_life.strategy_id or registered.strategy_name != native_life.strategy_id
                    or not 0 < total - prior <= native_life.filled_qty):
                raise ValueError("NATIVE_PROTECTION_OWNED_QUANTITY_CONFLICT")
        if plan is None and native_parent is None and total > prior and prior == 0 and any(t.symbol == request.symbol for t in self.trade_registry.snapshot()):
            raise ValueError("NATIVE_ORDER_EXISTING_POSITION_CONFLICT")
        result = ExecutionResult(symbol=request.symbol, trader_type=request.trader_type or "UNKNOWN",
            attempted=True, status=status, rationale="CACHED_BROKER_CALLBACK",
            client_order_id=order_id, ibkr_order_id=order["broker_order_id"], direction=request.direction,
            filled_quantity=total, remaining_quantity=remaining,
            average_fill_price=facts.get("avgFillPrice"), relationship_context=request.relationship_context)
        if plan is None and facts.get("avgFillPrice") is not None:
            # A cumulative average is not an order tick price. Preserve native
            # precision for delta accounting and exact replay comparison; the
            # generic result constructor quantizes ordinary money fields.
            result.average_fill_price = float(facts["avgFillPrice"])
        if plan is None and result_processor is None:
            raise RuntimeError("NATIVE_ORDER_PROCESSOR_REQUIRED")
        if result_processor is not None:
            in_progress = {"filled": total, "remaining": remaining, "status": status,
                "average_price": float(result.average_fill_price) if result.average_fill_price is not None else None}
            order["cached_update_in_progress"] = in_progress
            save()  # Durable boundary before any side effects.
        try:
            self._record_fill_and_position(request, result)
            self._release_strategy_allocation_for_terminal_result(request, result)
            self._release_capital_for_terminal_result(request, result)
            if result_processor is not None:
                from copy import copy
                processed = result
                if plan is None:
                    processed = copy(result)
                    processed.filled_quantity = total - prior
                    processed.average_fill_price = delta_price if total > prior else None
                    processed.execution_id = f"native:{order['broker_order_id']}:{total}:{facts.get('avgFillPrice')}"
                if plan is None:
                    self._native_processing_results.add(id(processed))
                try:
                    result_processor(processed)
                finally:
                    if plan is None:
                        self._native_processing_results.discard(id(processed))
                if plan is None and native_parent is None and total > prior:
                    life = self.post_fill_lifecycle.get_trade(order_id)
                    inventory = list(self._provider.get_open_orders())
                    self.post_fill_lifecycle.reconcile_orders(inventory, repair=False)
                    if (life is None or self._confirmed_stop_quantity(symbol=request.symbol, life=life, orders=inventory) is None
                            or not self.post_fill_lifecycle.assess_trade_stop_protection(order_id)["protected"]):
                        raise RuntimeError("NATIVE_ORDER_PROTECTION_UNVERIFIED")
                    order["protection_confirmed"] = True
                    from src.strategies.ross_momentum.strategy_policy import selected_completed_failure_profile
                    if request.setup_metadata and selected_completed_failure_profile(asdict(request)):
                        order["last_accounted_entry_fill_at"] = datetime.now(timezone.utc).isoformat()
                        matched = [row for row in inventory if str(row.order_id) == str(life.stop.broker_order_id)]
                        if len(matched) == 1:
                            con_id = matched[0].metadata.get("con_id")
                            if type(con_id) is int and con_id > 0:
                                order["security_id"] = con_id
                if native_parent is not None:
                    if native_life.filled_qty == 0 and native_parent.get("pmh_failure_exit"):
                        native_parent["pmh_failure_exit"]["status"] = "FILLED"
                    native_life.stop.status = status
                    position = manager.snapshot_positions().get(request.symbol) if manager else None
                    registered = self.trade_registry.get_trade(request.symbol, native_parent["request"].get("trader_type") or "UNKNOWN")
                    if ((position.quantity if position else 0) != native_life.filled_qty
                            or (registered.quantity if registered else 0) != native_life.filled_qty):
                        raise RuntimeError("NATIVE_PROTECTION_PROJECTION_UNVERIFIED")
                    self._verify_native_remaining_stop(order, native_life, total)
                if not order.get("lifecycle_application_rejected"):
                    order.pop("cached_update_in_progress")
                if plan is None:
                    order.update(filled=total, notional=(total*float(facts["avgFillPrice"]) if total > prior else order["notional"]),
                        status=status, terminal=status in terminal_statuses)
                save()
        except BaseException:
            if result_processor is not None:
                order["cached_update_in_progress"] = in_progress
                if plan is not None:
                    plan.paused = True
                else:
                    self._native_quarantined = True
                    self._failsafe_block_new_entries = True
            raise
        return result

    def _validate_native_binding(self, order_id, order, facts):
        scope = self._native_scope
        client = self._native_callback_client()
        request = order["request"]
        if (self._native_quarantined or scope is None or scope[0] != order["account"]
                or scope[1] is not client or order["mode"] != self.run_mode.value
                or order["symbol"] != request["symbol"].upper() or order["side"] != request["direction"].upper()
                or request["client_order_id"] != order_id or not order.get("decision_id")
                or not order_id.startswith(order["decision_id"]+"-")):
            raise ValueError("NATIVE_ORDER_BINDING_INVALID")
        from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
        if (RunMode(get_config("RUN_MODE_EFFECTIVE")) != self.run_mode or self.run_mode != RunMode.PAPER
                or not 0 <= (datetime.now(timezone.utc) - scope[2]).total_seconds() <= get_ibkr_snapshot_max_age_seconds()):
            raise ValueError("NATIVE_ORDER_SCOPE_STALE_OR_CHANGED")
        committed = (self._native_state or {}).get("orders", {}).get(order_id, {})
        if any(order.get(key) != committed.get(key) for key in
               ("request", "decision_id", "account", "mode", "symbol", "side", "broker_order_id", "requested",
                "protection_parent_order_id", "protection_trade_id", "security_id", "last_accounted_entry_fill_at", "pmh_failure_exit", "pmh_management_expired")):
            raise ValueError("NATIVE_ORDER_RETAINED_BINDING_CHANGED")
        facets = {"symbol": order["symbol"], "account": order["account"], "side": order["side"],
            "client_order_id": order_id, "orderId": order["broker_order_id"], "decision_id": order["decision_id"]}
        parent, life = self._native_protection_owner(order)
        if parent is not None:
            self._validate_native_binding(order["protection_parent_order_id"], parent, {})
            facets.update(client_order_id="PROTECT|" + life.trade_id, orderRef="PROTECT|" + life.trade_id,
                parentId=str(parent["broker_order_id"]))
        for key, expected in facets.items():
            actual = facts.get(key)
            if key == "side":
                actual = "BUY" if str(actual).upper() == "LONG" else str(actual).upper()
                expected = "BUY" if str(expected).upper() == "LONG" else str(expected).upper()
            if key in facts and str(actual) != str(expected):
                raise ValueError("NATIVE_ORDER_CALLBACK_IDENTITY_CONFLICT")

    def process_native_result(self, result, *, result_processor) -> bool:
        if id(result) in self._native_processing_results:
            return False
        order_id = str(result.client_order_id or "")
        order = self._native_orders.get(order_id)
        if order is None:
            if (not getattr(result, "relationship_context", None) and self.run_mode == RunMode.PAPER and self._provider is not None and self._provider.is_live()
                    and str(result.direction).upper() in {"LONG", "BUY"}
                    and (result.attempted or result.filled_quantity)):
                raise ValueError("NATIVE_ORDER_UNRETAINED_RESULT")
            return False
        if order.get("cached_update_in_progress") or self._native_quarantined:
            raise RuntimeError("NATIVE_ORDER_RECOVERY_REQUIRED")
        if not order.get("broker_order_id"):
            return True  # Uncertain transport retains ownership, never a fill.
        facts = {"filled": result.filled_quantity, "remaining": result.remaining_quantity,
            "status": result.status, "avgFillPrice": result.average_fill_price or result.entry_price,
            "symbol": result.symbol, "side": result.direction, "orderId": str(result.ibkr_order_id)}
        self._validate_native_binding(order_id, order, facts)
        self._consume_cached_order(None, order_id, order, facts, result_processor)
        return True

    def _native_protection_owner(self, order):
        parent_id = order.get("protection_parent_order_id")
        if parent_id is None:
            return None, None
        parent = self._native_orders.get(parent_id)
        if (parent is None or parent.get("protection_parent_order_id") is not None
                or parent.get("side") not in {"LONG", "BUY"}):
            raise ValueError("NATIVE_PROTECTION_PARENT_INVALID")
        life = self.post_fill_lifecycle.get_trade(order.get("protection_trade_id"))
        stop = life.stop if life is not None else None
        request = order["request"]
        initial = parent["request"]
        if (life is None or stop is None or not life.preserve_selected_protection or life.target is not None
                or life.symbol.upper() != parent["symbol"] or life.strategy_id != initial.get("strategy_name")
                or str(life.side).upper() not in {"LONG", "BUY"} or str(stop.side).upper() != "SELL"
                or stop.entry_intent_id != life.trade_id
                or stop.lifecycle_trade_id != life.trade_id or stop.strategy_owner != life.strategy_id
                or str(stop.entry_order_id) != str(parent.get("broker_order_id"))
                or str(stop.broker_order_id) != str(order.get("broker_order_id"))
                or request.get("order_type") != "STP" or order.get("side") != "SELL"
                or request.get("relationship_context") or request.get("quantity") != order.get("requested")
                or type(order.get("requested")) is not int or not 0 < order["requested"] <= parent["requested"]
                or order["requested"] != stop.quantity
                or order.get("decision_id") != parent.get("decision_id")
                or (order.get("account"), order.get("mode"), order.get("symbol")) != (parent.get("account"), parent.get("mode"), parent.get("symbol"))):
            raise ValueError("NATIVE_PROTECTION_BINDING_INVALID")
        return parent, life

    # Historical pmh_* durable keys retain their schema for restart inspection;
    # the retained explicit profile determines applicability, never the key name.
    def _pmh_complete_inventory(self):
        if self._native_scope is None:
            raise RuntimeError("PMH_CLOSE_ORDER_SCOPE_UNAVAILABLE")
        return list(self._provider.get_open_orders(require_complete=True, expected_client=self._native_scope[1]))

    def _pmh_working_close(self, parent, child, life, inventory, *, cumulative_filled=None):
        from numbers import Number
        matches = [row for row in inventory if str(row.order_id) == str(child["broker_order_id"])]
        if len(matches) != 1:
            return None
        row = matches[0]; meta = row.metadata
        total = meta.get("native_quantity")
        if (row.symbol != parent["symbol"] or row.parent_order_id != str(parent["broker_order_id"])
                or row.status.upper() not in {"SUBMITTED", "PRESUBMITTED"}
                or meta.get("side") != "SELL" or meta.get("order_ref") != "PROTECT|"+life.trade_id
                or type(meta.get("con_id")) is not int or meta["con_id"] != parent.get("security_id")
                or isinstance(total, bool) or not isinstance(total, Number)
                or total != child["requested"]
                or total-(child["filled"] if cumulative_filled is None else cumulative_filled) != life.filled_qty):
            return None
        if row.order_type.upper() == "STP" and meta.get("stop_price") == life.selected_stop_price:
            return "STP"
        if row.order_type.upper() == "MKT" and parent.get("pmh_failure_exit"):
            return "MKT"
        return None

    def request_selected_failure_exit(self, order_id, failure, *, decision):
        """Coordinate one existing owned close leg; never submit a second SELL."""
        from copy import deepcopy
        from src.strategies.ross_momentum.strategy_policy import selected_completed_failure_profile
        parent = self._native_orders[order_id]
        if (parent.get("pmh_failure_exit") or parent.get("pmh_management_expired") or not decision.allowed or decision.execution_blocked
                or decision.decision_id != parent["decision_id"] or decision.direction != "SELL"
                or not selected_completed_failure_profile(parent["request"])
                or failure.get("profile") != selected_completed_failure_profile(parent["request"])
                or failure.get("occurrence") != parent["request"].get("setup_metadata")):
            return False
        self._validate_native_binding(order_id, parent, {})
        life = self.post_fill_lifecycle.get_trade(order_id)
        if life is None or life.filled_qty != decision.max_position_size or life.filled_qty <= 0:
            return False
        self._retain_native_selected_stops()
        child_id = f"{order_id}:stop:{life.stop.broker_order_id}"
        child = self._native_orders.get(child_id)
        if child is None or child.get("terminal") or child.get("cached_update_in_progress"):
            return False
        self._validate_native_binding(child_id, child, {})
        inventory = self._pmh_complete_inventory()
        if any(row.symbol == parent["symbol"] and str(row.order_id) != str(child["broker_order_id"])
                and row.status.upper() not in {"FILLED", "CANCELLED", "CANCELED", "REJECTED", "INACTIVE"}
                for row in inventory):
            return False  # No overlapping pending quantity may be ignored.
        if (self._pmh_working_close(parent, child, life, inventory) != "STP"
                or not self.post_fill_lifecycle.assess_trade_stop_protection(order_id)["protected"]):
            return False
        self._validate_native_binding(order_id, parent, {})
        self._validate_native_binding(child_id, child, {})
        # Persist the exact selected occurrence, authorization and native total
        # BEFORE dispatch. An uncertain result never causes a retry/new identity.
        parent["pmh_failure_exit"] = {**deepcopy(failure), "status": "DISPATCH_UNCERTAIN",
            "native_order_id": child["broker_order_id"], "total_quantity": child["requested"],
            "owned_remainder": decision.max_position_size}
        self._save_native_orders()
        life.selected_exit_pending = deepcopy(parent["pmh_failure_exit"])
        self.post_fill_lifecycle.mark_exit_pending(order_id, failure["profile"].removesuffix("_V1"))
        self._failsafe_block_new_entries = True
        try:
            self._validate_native_binding(order_id, parent, {})
            self._validate_native_binding(child_id, child, {})
            self._provider.convert_selected_stop_to_market(broker_order_id=child["broker_order_id"],
                parent_order_id=parent["broker_order_id"], symbol=parent["symbol"],
                con_id=parent["security_id"], total_quantity=child["requested"],
                trade_id=life.trade_id, stop_price=life.selected_stop_price, expected_client=self._native_scope[1], scope_as_of=self._native_scope[2])
        except Exception as exc:
            parent["pmh_failure_exit"]["dispatch_error"] = type(exc).__name__
        # Return values are never broker confirmation. Independently read the
        # owned native order; MKT means exit pending, not STP certification.
        kind = self._pmh_working_close(parent, child, life, self._pmh_complete_inventory())
        parent["pmh_failure_exit"]["status"] = kind or "UNKNOWN"
        life.selected_exit_pending = deepcopy(parent["pmh_failure_exit"])
        self._save_native_orders()
        if kind is None:
            # Callback might have raced amendment: do not fabricate flat/fill.
            # The retained ID is consumed on the next authoritative fill pass.
            self._failsafe_block_new_entries = True
        return True

    request_pmh_failure_exit = request_selected_failure_exit

    def _verify_native_remaining_stop(self, order, life, cumulative_filled):
        if life.filled_qty <= 0:
            return
        parent = self._native_orders.get(order.get("protection_parent_order_id"), {})
        inventory = self._pmh_complete_inventory() if parent.get("pmh_failure_exit") else list(self._provider.get_open_orders())
        if parent.get("pmh_failure_exit"):
            kind = self._pmh_working_close(parent, order, life, inventory, cumulative_filled=cumulative_filled)
            if kind is None:
                raise RuntimeError("PMH_CLOSE_REMAINDER_UNVERIFIED")
            if parent["pmh_failure_exit"].get("status") != kind:
                parent["pmh_failure_exit"]["status"] = kind
                life.selected_exit_pending = dict(parent["pmh_failure_exit"])
                self._save_native_orders()
            return
        if self._confirmed_stop_quantity(symbol=order["symbol"], life=life,
                orders=inventory, stop_filled=cumulative_filled) is None:
            raise RuntimeError("NATIVE_PROTECTION_REMAINDER_UNVERIFIED")

    def _retain_native_selected_stops(self) -> None:
        for parent_id, parent in list(self._native_orders.items()):
            if parent.get("side") not in {"LONG", "BUY"} or not parent.get("protection_confirmed"):
                continue
            life = self.post_fill_lifecycle.get_trade(parent.get("protection_trade_id") or parent_id)
            if life is None or not life.preserve_selected_protection or life.target is not None or life.stop is None:
                continue  # Existing non-selected/targeted policies are outside this callback seam.
            try:
                self._validate_native_binding(parent_id, parent, {})
                stop = life.stop
                if not stop.broker_order_id or type(stop.quantity) is not int or stop.quantity <= 0:
                    raise ValueError("NATIVE_PROTECTION_BINDING_INVALID")
                broker_id = str(stop.broker_order_id)
                order_id = f"{parent_id}:stop:{broker_id}"
                if order_id in self._native_orders:
                    child = self._native_orders[order_id]
                    self._native_protection_owner(child)
                    continue
                if any(str(other.get("broker_order_id")) == broker_id for other in self._native_orders.values()):
                    raise ValueError("CACHED_EXECUTION_DUPLICATE_NATIVE_ID")
                initial = parent["request"]
                request = BrokerOrderRequest(client_order_id=order_id, symbol=parent["symbol"], direction="SELL",
                    quantity=stop.quantity, order_type="STP", trader_type=initial.get("trader_type"),
                    strategy_name=initial.get("strategy_name"), setup_family_id=initial.get("setup_family_id"),
                    trigger_id=initial.get("trigger_id"), target_model=initial.get("target_model"))
                retained = {"request": asdict(request), "decision_id": parent["decision_id"], "account": parent["account"],
                    "mode": parent["mode"], "symbol": parent["symbol"], "side": "SELL", "requested": stop.quantity,
                    "filled": 0, "notional": 0., "terminal": False, "status": "SUBMITTED", "broker_order_id": broker_id,
                    "protection_parent_order_id": parent_id, "protection_trade_id": life.trade_id}
                self._native_protection_owner(retained)
                self._native_orders[order_id] = retained
                self._save_native_orders()  # Retain the existing broker order; never dispatch a new stop/exit.
            except BaseException:
                self._quarantine_native_update(parent)
                raise

    def _quarantine_native_update(self, order, facts=None) -> None:
        if isinstance(facts, dict):
            def retained(value):
                if isinstance(value, float) and not math.isfinite(value):
                    return {"invalid_number": str(value)}
                if value is None or isinstance(value, (bool, int, float)):
                    return value
                if isinstance(value, str):
                    return value if len(value) <= 256 else {"prefix": value[:256], "truncated": True}
                return {"invalid_type": type(value).__name__[:64]}
            order["unresolved_update"] = {key: retained(facts[key]) for key in
                ("status", "filled", "remaining", "avgFillPrice", "symbol", "side", "account", "client_order_id", "orderId", "decision_id", "parentId", "orderRef") if key in facts}
        order["quarantine"] = "CALLBACK_PROCESSING_UNRESOLVED"
        self._mark_capital_recovery_failed("NATIVE_ORDER_PROCESSING_UNRESOLVED")
        self._native_quarantined = True
        self._failsafe_block_new_entries = True
        self._save_native_orders()

    def collect_relationship_updates(self, *, result_processor: Callable[[ExecutionResult], None] | None = None) -> list[ExecutionResult]:
        """Single enumeration of retained relationship and standalone callbacks."""
        manager = getattr(self, "relationship_manager", None)
        plans = list(manager._relationship_plans.values()) if manager else []
        entries = [(p, oid, o) for p in plans for oid, o in p.orders.items()]
        entries += [(None, oid, o) for oid, o in self._native_orders.items()]
        if any(o.get("cached_update_in_progress") or o.get("lifecycle_application_rejected") or o.get("owner_effect_pending") for _,_,o in entries):
            raise RuntimeError("CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED")
        if self._native_orders or (self.run_mode == RunMode.PAPER and self._provider is not None and callable(getattr(self._provider, "is_live", None)) and self._provider.is_live()):
            self._load_native_orders()
        def validate_enumeration(items):
            identities = [str(o["broker_order_id"]) for _,_,o in items if o.get("broker_order_id")]
            standalone_ids = {o.get("broker_order_id") for o in self._native_orders.values() if o.get("broker_order_id")}
            protection_ids = [str(p.protection_broker_order_id) for p in plans if p.protection_broker_order_id]
            if (len(identities) != len(set(identities)) or len({oid for _,oid,_ in items}) != len(items)
                    or len(protection_ids) != len(set(protection_ids))
                    or any(identity in standalone_ids for identity in protection_ids)):
                raise ValueError("CACHED_EXECUTION_DUPLICATE_NATIVE_ID")
        validate_enumeration(entries)
        for plan in plans:
            manager.cancel_excess_milestone_orders(plan)
            if plan.pending_stop_resize:
                life = self.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
                if life is not None and life.filled_qty > 0:
                    self.post_fill_lifecycle.update_selected_exposure(trade_id=life.trade_id,
                        filled_qty=life.filled_qty, avg_fill_price=life.avg_fill_price)
                self._failsafe_block_new_entries = True
            if plan.pending_stop_cancel and self._provider is not None:
                try:
                    self._provider.cancel_order(broker_order_id=plan.pending_stop_cancel)
                except Exception:
                    self._failsafe_block_new_entries = True
        reader = getattr(self._provider, "cached_order_update", None)
        if not callable(reader):
            return []
        for plan in plans:
            self._retain_relationship_stop_fill(plan, reader)
        self._retain_native_selected_stops()
        entries = [(p,oid,o) for p in plans for oid,o in list(p.orders.items())]
        entries += [(None,oid,o) for oid,o in list(self._native_orders.items())]
        validate_enumeration(entries)
        results = []
        for plan,order_id,order in entries:
            checkpoint()
            if plan is not None and order.get("release_reservation") and order.get("request"):
                request = BrokerOrderRequest(**order["request"])
                self._release_strategy_allocation_for_order(request, reason="SUBMISSION_RECONCILED_ABSENT")
                self._release_capital_for_order(request, reason="SUBMISSION_RECONCILED_ABSENT")
                order["release_reservation"] = False
                manager._save_relationship_state()
            if not order.get("broker_order_id") or not order.get("request"):
                continue
            facts = None
            try:
                if plan is None:
                    self._validate_native_binding(order_id, order, {})
                facts = reader(order["broker_order_id"])
                if not facts:
                    if (plan is None and order.get("protection_parent_order_id") and (order["filled"]
                            or self._native_orders[order["protection_parent_order_id"]].get("pmh_failure_exit"))):
                        _, life = self._native_protection_owner(order)
                        self._verify_native_remaining_stop(order, life, order["filled"])
                    continue
                if plan is None:
                    self._validate_native_binding(order_id, order, facts)
                checkpoint()
                result = self._consume_cached_order(plan, order_id, order, facts, result_processor)
            except BaseException:
                if plan is None:
                    self._quarantine_native_update(order, facts)
                raise
            if result is not None:
                results.append(result)
        return results

    def _get_open_trades_for_symbol(self, symbol: str) -> list[str]:
        return self.post_fill_lifecycle._get_open_trades_for_symbol(symbol)

    def _run_live_probe_exit_if_needed(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        if self.run_mode != RunMode.LIVE:
            return
        if not bool(get_config("LIVE_EXECUTION_PROBE_MODE")):
            return
        if str(request.strategy_name or "").upper() != "LIVE_EXECUTION_PROBE":
            return
        if str(request.direction).upper() != "LONG":
            return
        filled_quantity = int(getattr(result, "filled_quantity", 0) or 0)
        if filled_quantity <= 0:
            return

        hold_seconds = int(get_config("PROBE_HOLD_SECONDS") or 60)
        print(f"[PROBE][FILLED] symbol={request.symbol} qty={filled_quantity}")
        print(f"[PROBE][HOLD] symbol={request.symbol} seconds={hold_seconds}")
        time.sleep(max(0, hold_seconds))
        exit_order = BrokerOrderRequest(
            client_order_id=f"{request.client_order_id}-EXIT",
            symbol=request.symbol,
            direction="SELL",
            quantity=filled_quantity,
            order_type="MKT",
            trader_type=request.trader_type,
            strategy_name=request.strategy_name,
            attempt_number=1,
            created_tick=request.created_tick,
            stop_loss_price=None,
            take_profit_price=None,
            pattern_name=request.pattern_name,
            invalidation_level=request.invalidation_level,
            next_retry_tick=None,
        )
        print(f"[PROBE][EXIT_INTENT] symbol={request.symbol} side=SELL close_position=True")
        print(f"[PROBE][SELL] symbol={request.symbol} qty={filled_quantity}")
        self._record_order_stage(request.client_order_id, "EXIT")
        exit_result = self._provider.place_order(exit_order)
        self._confirm_broker_ack(exit_order, exit_result)
        self._record_fill_and_position(exit_order, exit_result)
        print(
            f"[PROBE][CLOSED] symbol={request.symbol} status={getattr(exit_result, 'status', 'UNKNOWN')}"
        )

    def _record_order_stage(self, client_order_id: str, stage: str) -> None:
        stages = self._order_trace_stages.setdefault(client_order_id, set())
        stages.add(stage)

    def _validate_trace_integrity(self, client_order_id: str) -> None:
        required = {"SUBMIT", "ACK", "FILL"}
        if client_order_id in self._require_exit_stage:
            required.add("EXIT")
        stages = self._order_trace_stages.get(client_order_id, set())
        missing = sorted(required - stages)
        if missing:
            self.execution_integrity_flag = True
            print(
                f"[EXECUTION][INTEGRITY] order_id={client_order_id} "
                f"missing_stages={','.join(missing)} execution_integrity_flag=True"
            )

    def _log_ibkr_status(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        normalized = str(getattr(result, "status", "UNKNOWN") or "UNKNOWN")
        ibkr_order_id = getattr(result, "ibkr_order_id", None)
        order_id_display = ibkr_order_id if ibkr_order_id is not None else "MISSING"
        print(f"[EXECUTION][IBKR] order_id={order_id_display} status={normalized}")
        print(
            f"[IBKR][ORDER_STATUS] order_id={order_id_display} "
            f"symbol={request.symbol} status={normalized}"
        )
        if normalized == "Filled" and getattr(result, "filled_quantity", 0) > 0:
            print(f"[EXECUTION][IBKR] order_id={order_id_display} status=FILLED")
        if normalized in {"BLOCKED", "FAILED", "REJECTED", "TIMED_OUT"}:
            print(
                f"[IBKR][ORDER_ERROR] order_id={order_id_display} "
                f"symbol={request.symbol} status={normalized}"
            )
            print(f"[EXECUTION][IBKR] order_id={order_id_display} status=REJECTED")
            reason = getattr(result, "rejection_reason", None) or getattr(result, "rationale", None) or "UNKNOWN"
            code = getattr(result, "broker_error_code", None) or "UNKNOWN"
            print(f"[EXECUTION][REJECT] symbol={request.symbol} reason={reason} code={code}")
            self._execution_log(
                "REJECT",
                symbol=request.symbol,
                strategy_id=request.strategy_name,
                run_mode=self.run_mode.value,
                side=request.direction,
                qty=request.quantity,
                broker_order_id=order_id_display,
                status=normalized,
                reason=reason,
            )
        if normalized in {"CANCELLED", "CANCELED"}:
            print(f"[EXECUTION][IBKR] order_id={order_id_display} status=CANCELLED")

    def _release_strategy_allocation_for_decision(self, risk_decision: RiskDecision, *, reason: str) -> None:
        decision_id = getattr(risk_decision, "strategy_allocation_decision_id", None)
        if not decision_id:
            return
        self.strategy_allocation_authority.release_reservation(
            decision_id=decision_id,
            reason=reason,
        )

    def _release_strategy_allocation_for_order(self, request: BrokerOrderRequest, *, reason: str) -> None:
        decision_id = self._strategy_allocation_decisions_by_order_id.get(request.client_order_id)
        if not decision_id:
            return
        self.strategy_allocation_authority.release_reservation(
            decision_id=decision_id,
            order_id=request.client_order_id,
            reason=reason,
        )

    def _release_strategy_allocation_for_terminal_result(
        self,
        request: BrokerOrderRequest,
        result: ExecutionResult,
        *,
        retry_enqueued: bool = False,
    ) -> None:
        native = self._native_orders.get(request.client_order_id)
        if native is not None and (not native.get("broker_order_id") or str(result.status).upper() not in {"FILLED", "REJECTED", "CANCELLED", "CANCELED", "INACTIVE"}):
            return
        if bool(getattr(result, "retry_scheduled", False)) and retry_enqueued:
            return
        if bool(getattr(result, "retry_scheduled", False)) and not retry_enqueued:
            self._release_strategy_allocation_for_order(request, reason="RETRY_NOT_SCHEDULED")
            return
        if int(getattr(result, "filled_quantity", 0) or 0) > 0 and not request.relationship_context and native is None:
            return
        status = str(getattr(result, "status", "") or "").upper()
        if (status in {"BLOCKED", "FAILED", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "NOT_FILLED", "TIMED_OUT"}
                or ((request.relationship_context or native is not None) and (status == "INACTIVE"
                    or (status == "SIMULATED" and not bool(getattr(result, "retry_scheduled", False)))))):
            self._release_strategy_allocation_for_order(request, reason=f"ORDER_{status}")

    def _release_capital_for_order(self, request: BrokerOrderRequest, *, reason: str) -> None:
        decision_id = self._capital_decisions_by_order_id.get(request.client_order_id)
        if not decision_id:
            return
        self.capital_authority.release_reservation(
            decision_id=decision_id,
            order_id=request.client_order_id,
            reason=reason,
        )

    def _release_capital_for_terminal_result(
        self,
        request: BrokerOrderRequest,
        result: ExecutionResult,
        *,
        retry_enqueued: bool = False,
    ) -> None:
        native = self._native_orders.get(request.client_order_id)
        if native is not None and (not native.get("broker_order_id") or str(result.status).upper() not in {"FILLED", "REJECTED", "CANCELLED", "CANCELED", "INACTIVE"}):
            return
        if bool(getattr(result, "retry_scheduled", False)) and retry_enqueued:
            return
        if bool(getattr(result, "retry_scheduled", False)) and not retry_enqueued:
            self._release_capital_for_order(request, reason="RETRY_NOT_SCHEDULED")
            return
        if int(getattr(result, "filled_quantity", 0) or 0) > 0 and not request.relationship_context and native is None:
            return
        status = str(getattr(result, "status", "") or "").upper()
        if (status in {"BLOCKED", "FAILED", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "NOT_FILLED", "TIMED_OUT"}
                or ((request.relationship_context or native is not None) and (status == "INACTIVE"
                    or (status == "SIMULATED" and not bool(getattr(result, "retry_scheduled", False)))))):
            self._release_capital_for_order(request, reason=f"ORDER_{status}")

    def _convert_capital_for_fill(
        self,
        request: BrokerOrderRequest,
        *,
        filled_quantity: int,
        fill_price: float,
        effect_evidence: dict | None = None,
    ) -> None:
        decision_id = self._capital_decisions_by_order_id.get(request.client_order_id)
        self.capital_authority.convert_reservation_to_exposure(
            decision_id=decision_id,
            order_id=request.client_order_id,
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            fill_quantity=filled_quantity,
            fill_price=fill_price,
            trade_id=request.client_order_id,
            reason="ENTRY_FILL",
            **({"effect_evidence": effect_evidence} if effect_evidence is not None else {}),
        )

    def _convert_strategy_allocation_for_fill(
        self,
        request: BrokerOrderRequest,
        *,
        filled_quantity: int,
        fill_price: float,
        effect_evidence: dict | None = None,
    ) -> None:
        decision_id = self._strategy_allocation_decisions_by_order_id.get(request.client_order_id)
        self.strategy_allocation_authority.convert_reservation_to_exposure(
            decision_id=decision_id,
            order_id=request.client_order_id,
            strategy_id=request.strategy_name,
            symbol=request.symbol,
            fill_quantity=filled_quantity,
            fill_price=fill_price,
            trade_id=request.client_order_id,
            reason="ENTRY_FILL",
            **({"effect_evidence": effect_evidence} if effect_evidence is not None else {}),
        )

    def _clamp_order_quantity(self, quantity: int, *, symbol: str) -> int:
        if self.max_shares_per_order is None:
            return quantity
        clamped = min(max(1, int(quantity)), int(self.max_shares_per_order))
        if clamped != quantity:
            print(
                "[RISK][MICRO_CLAMP] "
                f"symbol={symbol} requested_qty={quantity} clamped_qty={clamped} "
                f"max_shares_per_order={self.max_shares_per_order}"
            )
        return clamped

    def _effective_quantity_from_risk_decision(self, risk_decision: Optional[RiskDecision]) -> int:
        if risk_decision is None:
            return 0
        raw_quantity = int(getattr(risk_decision, "max_position_size", 0) or 0)
        if str(getattr(risk_decision, "strategy_name", "")).upper() == "LIVE_EXECUTION_PROBE":
            raw_quantity = 1
        normalized_quantity = max(1, raw_quantity)
        return self._clamp_order_quantity(normalized_quantity, symbol=risk_decision.symbol)

    def _blocked_execution_from_risk_decision(
        self, risk_decision: Optional[RiskDecision], rationale: str = "EXECUTION_DISABLED"
    ) -> ExecutionResult:
        if risk_decision is None:
            symbol = "UNKNOWN"
            trader_type = "MANUAL"
            direction = "UNKNOWN"
            quantity = 0
            strategy_name = "UNKNOWN"
        else:
            symbol = risk_decision.symbol
            trader_type = risk_decision.trader_type
            direction = risk_decision.direction
            quantity = self._effective_quantity_from_risk_decision(risk_decision)
            strategy_name = risk_decision.strategy_name

        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": symbol,
                "trader_type": trader_type,
                "strategy_name": strategy_name,
                "direction": direction,
                "requested_quantity": quantity,
                "run_mode": self.run_mode.value,
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
                "reason": rationale,
            },
        )
        self._execution_log(
            "STATE_UPDATE",
            symbol=symbol,
            intent_id=getattr(risk_decision, "intent_id", None) if risk_decision else None,
            strategy_id=strategy_name,
            run_mode=self.run_mode.value,
            side=direction,
            qty=quantity,
            status="BLOCKED",
            reason=rationale,
        )
        return ExecutionResult(
            symbol=symbol,
            trader_type=trader_type,
            attempted=False,
            status="BLOCKED",
            rationale=rationale,
            direction=direction,
            quantity=quantity,
            stop_loss_price=getattr(risk_decision, "stop_loss_price", None),
            take_profit_price=getattr(risk_decision, "take_profit_price", None),
            requested_quantity=quantity,
            filled_quantity=0,
            remaining_quantity=quantity,
            fill_status="NONE",
            note=rationale,
            rejection_reason=rationale,
        )

    def _blocked_execution_from_request(
        self, request: BrokerOrderRequest
    ) -> ExecutionResult:
        rationale = "EXECUTION_DISABLED"
        self.event_collector.emit(
            event_type="ORDER_BLOCKED_READONLY",
            source="ExecutionEngine",
            payload={
                "symbol": request.symbol,
                "trader_type": request.trader_type or "UNKNOWN",
                "strategy_name": request.strategy_name or "UNKNOWN",
                "direction": request.direction,
                "requested_quantity": request.quantity,
                "run_mode": self.run_mode.value,
                "execution_enabled": self.execution_enabled,
                "readonly_enabled": get_ibkr_readonly_enabled(),
                "reason": rationale,
            },
        )
        self._execution_log(
            "STATE_UPDATE",
            symbol=request.symbol,
            strategy_id=request.strategy_name,
            run_mode=self.run_mode.value,
            side=request.direction,
            qty=request.quantity,
            status="BLOCKED",
            reason=rationale,
        )
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status="BLOCKED",
            rationale=rationale,
            direction=request.direction,
            quantity=request.quantity,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            note="EXECUTION_DISABLED",
            rejection_reason="EXECUTION_DISABLED",
            attempt_number=request.attempt_number,
            client_order_id=request.client_order_id,
            retry_scheduled=False,
            next_retry_tick=None,
        )

    def _schedule_retry(self, request: BrokerOrderRequest, result: ExecutionResult) -> bool:
        if request.relationship_context or request.client_order_id in self._native_orders:
            return False  # reconciliation owns any remaining logical action
        if not self.execution_enabled:
            return False
        if not getattr(result, "retry_scheduled", False) or result.next_retry_tick is None:
            return False

        next_attempt = request.attempt_number + 1
        max_attempts = self._max_attempts(request.trader_type or "")
        if next_attempt > max_attempts:
            print(
                f"[RETRY] id={request.client_order_id} reached max attempts; not scheduling further retries."
            )
            return False

        self._assert_execution_enabled_for_order_construction("retry schedule")
        scheduled_request = BrokerOrderRequest(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            direction=request.direction,
            quantity=request.quantity,
            order_type=request.order_type,
            trader_type=request.trader_type,
            strategy_name=request.strategy_name,
            attempt_number=next_attempt,
            created_tick=result.next_retry_tick,
            stop_loss_price=request.stop_loss_price,
            take_profit_price=request.take_profit_price,
            pattern_name=request.pattern_name,
            invalidation_level=request.invalidation_level,
            next_retry_tick=result.next_retry_tick,
            setup_family_id=request.setup_family_id,
            trigger_id=request.trigger_id,
            target_model=request.target_model,
            relationship_context=request.relationship_context,
        )
        self.pending_book.add(scheduled_request)
        print(
            f"[PENDING] Added retry for id={request.client_order_id} "
            f"attempt={next_attempt} tick={result.next_retry_tick}"
        )
        return True

    def _assert_execution_enabled_for_order_construction(self, context: str) -> None:
        if not self.execution_enabled:
            raise RuntimeError(
                "Execution disabled: order construction blocked "
                f"(context={context})."
            )

    def emit_cycle_execution_summary(self) -> None:
        orders_submitted = self.event_collector.cycle_count("ORDER_SUBMISSION_ATTEMPTED")
        orders_acknowledged = self.event_collector.cycle_count("ORDER_SUBMITTED_ACK")
        orders_filled = self.event_collector.cycle_count("ORDER_FILL_RECORDED")
        orders_rejected = (
            self.event_collector.cycle_count("ORDER_SUBMISSION_FAILED")
            + self.event_collector.cycle_count("ORDER_SUBMISSION_BLOCKED")
        )
        print(
            "[EXECUTION_SUMMARY]\n"
            f"orders_submitted={orders_submitted}\n"
            f"orders_acknowledged={orders_acknowledged}\n"
            f"orders_filled={orders_filled}\n"
            f"orders_rejected={orders_rejected}\n"
            f"orders_simulated={self.event_collector.cycle_count('ORDER_SIMULATED')}"
        )

    def complete_trade(self, symbol: str, trader_type: str) -> None:
        """
        Teaching helper to remove an active trade when a lifecycle ends.

        No broker integration; purely updates the in-memory registry.
        """

        self.trade_registry.unregister_trade(symbol, trader_type)
        print(
            "[EXECUTION:REGISTRY] Completed trade "
            f"symbol={symbol} trader_type={trader_type}; "
            f"remaining active={self.trade_registry.count_active_by_trader(trader_type)}"
        )

    def close_all_active_trades(self):
        """
        Teaching-first lifecycle reset.

        Closes and deregisters all active trades so capacity is freed in the
        ActiveTradeRegistry for future cycles.
        """

        closed_trades = self.trade_registry.close_all_trades()
        if not closed_trades:
            print("[EXECUTION:REGISTRY] No active trades to close — registry already empty.")
            return []

        print("[EXECUTION:REGISTRY] Closing all active trades and resetting registry")
        for trade in closed_trades:
            print(
                "[EXECUTION:REGISTRY] Closed trade "
                f"symbol={getattr(trade, 'symbol', 'UNKNOWN')} "
                f"trader_type={getattr(trade, 'trader_type', 'UNKNOWN')}"
            )

        print(
            "[EXECUTION:REGISTRY] All trades closed; registry capacity reset for next cycle"
        )
        return closed_trades

    def shutdown(self) -> None:
        """
        Idempotent shutdown placeholder.

        Future implementation will release broker resources, cancel orders,
        and flush telemetry. For now this acts as a structural hook to enable
        safe orchestrator shutdown sequencing.
        """

        broker = getattr(self._provider, "broker", None)
        if broker is not None and hasattr(broker, "disconnect"):
            broker.disconnect(reason="execution_engine_shutdown")
        print("[EXECUTION] Shutdown requested — broker cleanup complete.")
