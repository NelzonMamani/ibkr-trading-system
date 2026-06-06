"""
Execution engine that routes through a broker adapter with deterministic retry semantics.
"""

import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

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

    def _run_protection_reconciliation(self, *, open_orders: list[object] | None = None, reason: str = "runtime") -> None:
        if self._provider is None:
            return
        try:
            broker_orders = list(open_orders) if open_orders is not None else list(self._provider.get_open_orders())
        except Exception as exc:
            print(f"[LIFECYCLE][RECONCILIATION][ERROR] stage=fetch_open_orders reason={exc}")
            return
        summary = self.post_fill_lifecycle.reconcile_orders(broker_orders, repair=True)
        self._failsafe_block_new_entries = bool(summary.get("block_new_entries", False))
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
        )

    def execute_trade(self, risk_decision: Optional[RiskDecision]) -> ExecutionResult:
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

        autonomous_recovery_result = self._autonomous_recovery_preflight_check(risk_decision)
        if autonomous_recovery_result is not None:
            return autonomous_recovery_result

        if self.startup_recovery_complete():
            daily_risk_result = self._daily_risk_preflight_check(risk_decision)
            if daily_risk_result is not None:
                return daily_risk_result

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
        )
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
            f"[ORDER_SUBMITTED] symbol={request.symbol} qty={request.quantity} type={request.order_type}"
        )
        try:
            result = self._provider.place_order(request)
        except Exception as exc:
            self._release_strategy_allocation_for_order(request, reason="ENTRY_SUBMISSION_FAILURE")
            self._release_capital_for_order(request, reason="ENTRY_SUBMISSION_FAILURE")
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="FAILED",
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
        if str(getattr(result, "status", "") or "") in self.VALID_IBKR_STATUSES:
            print(
                f"[EXECUTION] SUBMITTED symbol={request.symbol} qty={request.quantity} "
                f"order_id={getattr(result, 'ibkr_order_id', None)}"
            )
            if str(request.direction).upper() == "SELL":
                print(
                    f"[EXIT][SUBMIT] symbol={request.symbol} qty={request.quantity} "
                    f"broker_order_id={getattr(result, 'ibkr_order_id', None)}"
                )
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
        self._log_ibkr_status(request, result)
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
        if ibkr_order_id is None:
            reason = "reason=NO_IBKR_ORDER_ID"
            print(f"[EXECUTION][ERROR] order_id=MISSING {reason}")
            self.execution_integrity_flag = True
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale=reason,
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note=reason,
                rejection_reason=reason,
                broker_error_code=str(getattr(result, "broker_error_code", "") or "") or None,
                broker_error_message=getattr(result, "broker_error_message", None),
                client_order_id=request.client_order_id,
                ibkr_order_id=None,
                attempt_number=request.attempt_number,
            )

        if status_raw not in self.VALID_IBKR_STATUSES:
            reason = f"reason=INVALID_IBKR_STATUS:{status_raw or 'UNKNOWN'}"
            print(f"[EXECUTION][ERROR] order_id={ibkr_order_id} {reason}")
            self.execution_integrity_flag = True
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="BLOCKED",
                rationale=reason,
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note=reason,
                rejection_reason=reason,
                broker_error_code=str(getattr(result, "broker_error_code", "") or "") or None,
                broker_error_message=getattr(result, "broker_error_message", None),
                client_order_id=request.client_order_id,
                ibkr_order_id=ibkr_order_id,
                attempt_number=request.attempt_number,
            )

        status_upper = status_raw.upper()
        if not status_raw or status_upper == "UNKNOWN":
            print(
                f"[EXECUTION][ERROR] order_id={ibkr_order_id} reason=no_broker_ack"
            )
            self.execution_integrity_flag = True
            return ExecutionResult(
                symbol=request.symbol,
                trader_type=request.trader_type or "UNKNOWN",
                attempted=False,
                status="FAILED",
                rationale="no_broker_ack",
                direction=request.direction,
                quantity=request.quantity,
                requested_quantity=request.quantity,
                filled_quantity=0,
                remaining_quantity=request.quantity,
                fill_status="NONE",
                note="no_broker_ack",
                rejection_reason="no_broker_ack",
                broker_error_code=str(getattr(result, "broker_error_code", "") or "") or None,
                broker_error_message=getattr(result, "broker_error_message", None),
                client_order_id=request.client_order_id,
                ibkr_order_id=ibkr_order_id,
                attempt_number=request.attempt_number,
            )

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

    def _record_fill_and_position(self, request: BrokerOrderRequest, result: ExecutionResult) -> None:
        filled_quantity = int(getattr(result, "filled_quantity", 0) or 0)
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
        if direction_upper in {"LONG", "BUY", "SHORT"}:
            self._convert_strategy_allocation_for_fill(request, filled_quantity=filled_quantity, fill_price=fill_price)
            self._convert_capital_for_fill(request, filled_quantity=filled_quantity, fill_price=fill_price)
        elif direction_upper == "SELL":
            self.strategy_allocation_authority.release_exposure(
                strategy_id=request.strategy_name or "UNKNOWN",
                quantity=filled_quantity,
                price=fill_price,
                reason="EXIT_FILL",
            )
            self.capital_authority.release_exposure(
                symbol=request.symbol,
                quantity=filled_quantity,
                price=fill_price,
                strategy_id=request.strategy_name,
                reason="EXIT_FILL",
            )
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
            "filled_qty": filled_quantity,
            "entry_price": entry_price,
            "timestamp": time.time(),
        }
        if direction_upper in {"LONG", "BUY"}:
            protection_result = self.post_fill_lifecycle.activate_trade_management_after_fill(
                trade_id=request.client_order_id,
                symbol=request.symbol,
                side=request.direction,
                filled_qty=filled_quantity,
                avg_fill_price=float(entry_price or 0.0),
                strategy_id=request.strategy_name or "UNKNOWN",
                intended_qty=request.quantity,
                session_label=self.run_mode.value,
            )
            self.position_records[request.client_order_id]["lifecycle"] = protection_result
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
        if bool(getattr(result, "retry_scheduled", False)) and retry_enqueued:
            return
        if bool(getattr(result, "retry_scheduled", False)) and not retry_enqueued:
            self._release_strategy_allocation_for_order(request, reason="RETRY_NOT_SCHEDULED")
            return
        if int(getattr(result, "filled_quantity", 0) or 0) > 0:
            return
        status = str(getattr(result, "status", "") or "").upper()
        if status in {"BLOCKED", "FAILED", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "NOT_FILLED", "TIMED_OUT"}:
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
        if bool(getattr(result, "retry_scheduled", False)) and retry_enqueued:
            return
        if bool(getattr(result, "retry_scheduled", False)) and not retry_enqueued:
            self._release_capital_for_order(request, reason="RETRY_NOT_SCHEDULED")
            return
        if int(getattr(result, "filled_quantity", 0) or 0) > 0:
            return
        status = str(getattr(result, "status", "") or "").upper()
        if status in {"BLOCKED", "FAILED", "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "NOT_FILLED", "TIMED_OUT"}:
            self._release_capital_for_order(request, reason=f"ORDER_{status}")

    def _convert_capital_for_fill(
        self,
        request: BrokerOrderRequest,
        *,
        filled_quantity: int,
        fill_price: float,
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
        )

    def _convert_strategy_allocation_for_fill(
        self,
        request: BrokerOrderRequest,
        *,
        filled_quantity: int,
        fill_price: float,
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
