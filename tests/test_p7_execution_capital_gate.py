from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.capital_management_authority import CapitalManagementAuthority
from src.core.event_collector import EventCollector
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import OrderSnapshot, PositionSnapshot
from src.execution.startup_recovery_authority import RecoveryState, StartupRecoveryResult
from src.models.data_models import RiskDecision
from src.models.execution_result import ExecutionResult
from src.sim.price_feed import DeterministicPriceFeed


@pytest.fixture(autouse=True)
def _live_execution_config() -> None:
    set_config_overrides(
        {
            "RUN_MODE": "LIVE",
            "EXECUTION_ENABLED": True,
            "IBKR_READONLY_ENABLED": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": True,
            "RISK_ACCOUNT_EQUITY": 10_000.0,
            "RISK_MAX_OPEN_POSITIONS": 5,
            "LIFECYCLE_MAX_POSITIONS": 5,
            "LIFECYCLE_MAX_POSITION_EXPOSURE": 1_500.0,
            "LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 5_000.0,
            "RISK_MAX_TOTAL_EXPOSURE_PCT": 50.0,
        }
    )
    yield
    set_config_overrides(None)


class _CapitalGateProvider:
    def __init__(self, *, available_funds: float = 10_000.0, buying_power: float = 10_000.0) -> None:
        self.available_funds = available_funds
        self.buying_power = buying_power
        self.submitted_orders: list[object] = []
        self.protective_orders: list[OrderSnapshot] = []

    def name(self) -> str:
        return "P7_CAPITAL_TEST_PROVIDER"

    def is_live(self) -> bool:
        return True

    def get_account_summary(self) -> dict[str, float]:
        return {
            "NetLiquidation": 10_000.0,
            "AvailableFunds": self.available_funds,
            "BuyingPower": self.buying_power,
        }

    def get_positions(self) -> PositionSnapshot:
        return PositionSnapshot(positions=[], as_of="2026-06-04T12:00:00+00:00")

    def get_open_orders(self) -> list[OrderSnapshot]:
        return list(self.protective_orders)

    def place_order(self, request):
        self.submitted_orders.append(request)
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=True,
            status="Filled",
            rationale="p7_test_fill",
            direction=request.direction,
            quantity=request.quantity,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            remaining_quantity=0,
            fill_status="FULL",
            average_fill_price=Decimal("10.00"),
            client_order_id=request.client_order_id,
            ibkr_order_id=1001,
            attempt_number=request.attempt_number,
        )

    def cancel(self, order_id: str):
        return {"order_id": order_id, "status": "NOT_SUPPORTED", "rationale": "test"}

    def place_stop_order(self, **kwargs):
        order_id = f"STOP-{len(self.protective_orders) + 1}"
        self.protective_orders.append(
            OrderSnapshot(
                order_id=order_id,
                symbol=kwargs["symbol"],
                status="Submitted",
                order_type="STP",
                parent_order_id=kwargs.get("parent_order_id"),
                metadata={
                    "side": kwargs["side"],
                    "quantity": kwargs["quantity"],
                    "stop_price": kwargs["stop_price"],
                    "trade_id": kwargs["trade_id"],
                },
            )
        )
        return {"broker_order_id": order_id, "status": "Submitted", "order_type": "STP"}

    def place_target_order(self, **kwargs):
        order_id = f"TGT-{len(self.protective_orders) + 1}"
        self.protective_orders.append(
            OrderSnapshot(
                order_id=order_id,
                symbol=kwargs["symbol"],
                status="Submitted",
                order_type="LMT",
                parent_order_id=kwargs.get("parent_order_id"),
                metadata={
                    "side": kwargs["side"],
                    "quantity": kwargs["quantity"],
                    "limit_price": kwargs["limit_price"],
                    "trade_id": kwargs["trade_id"],
                },
            )
        )
        return {"broker_order_id": order_id, "status": "Submitted", "order_type": "LMT"}

    def modify_stop_order(self, **kwargs):
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, *, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


class _RetryFlagProvider(_CapitalGateProvider):
    def __init__(
        self,
        *,
        status: str = "Submitted",
        retry_scheduled: bool = True,
        next_retry_tick: int | None = 1,
    ) -> None:
        super().__init__(available_funds=10_000.0, buying_power=10_000.0)
        self.status = status
        self.retry_scheduled = retry_scheduled
        self.next_retry_tick = next_retry_tick
        self.engine_to_disable = None

    def place_order(self, request):
        self.submitted_orders.append(request)
        if self.engine_to_disable is not None:
            self.engine_to_disable.execution_enabled = False
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=False,
            status=self.status,
            rationale=self.status,
            direction=request.direction,
            quantity=0,
            requested_quantity=request.quantity,
            filled_quantity=0,
            remaining_quantity=request.quantity,
            fill_status="NONE",
            client_order_id=request.client_order_id,
            ibkr_order_id=1001,
            attempt_number=request.attempt_number,
            retry_scheduled=self.retry_scheduled,
            next_retry_tick=self.next_retry_tick,
            rejection_reason=self.status,
        )


def _risk_decision(*, quantity: int = 1, trader_type: str = "P7_TEST") -> RiskDecision:
    return RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=quantity,
        risk_level="LOW",
        rationale="p7 capital gate",
        trader_type=trader_type,
        strategy_name="unit_strategy",
        direction="BUY",
        stop_loss_price=9.0,
        decision_id=f"risk-p7-{quantity}",
        intent_id=f"intent-p7-{quantity}",
    )


def _engine(
    provider: _CapitalGateProvider,
    authority: CapitalManagementAuthority | None = None,
    trade_registry: ActiveTradeRegistry | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        provider=provider,
        trade_registry=trade_registry or ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        capital_authority=authority,
    )


def test_execution_does_not_submit_when_capital_denies_approval() -> None:
    provider = _CapitalGateProvider(available_funds=5.0, buying_power=5.0)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_INSUFFICIENT_CAPITAL")
    assert provider.submitted_orders == []
    assert engine.capital_authority.active_reservations == {}


def test_force_execute_cannot_bypass_capital_gate() -> None:
    provider = _CapitalGateProvider(available_funds=5.0, buying_power=5.0)
    engine = _engine(provider)
    decision = _risk_decision(quantity=1)
    decision.force_execute = True

    result = engine.execute_trade(decision)

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_INSUFFICIENT_CAPITAL")
    assert provider.submitted_orders == []


def test_executable_capital_decision_allows_submission_and_converts_reservation() -> None:
    provider = _CapitalGateProvider(available_funds=10_000.0, buying_power=10_000.0)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1
    assert engine.capital_authority.total_reserved_capital == 0.0
    assert engine.capital_authority.symbol_exposure("AAPL") == 10.0


def test_trade_management_add_to_existing_symbol_at_max_positions_reaches_broker() -> None:
    registry = ActiveTradeRegistry()
    for symbol in ("AAPL", "MSFT", "NVDA", "TSLA", "AMD"):
        registry.register_trade(
            ActiveTrade(
                symbol=symbol,
                trader_type="P7_TEST",
                entry_tick=0,
                entry_price=10.0,
                direction="LONG",
                quantity=1,
                strategy_name="unit_strategy",
                stop_loss_price=9.0,
            )
        )
    provider = _CapitalGateProvider(available_funds=10_000.0, buying_power=10_000.0)
    engine = _engine(provider, trade_registry=registry)
    decision = _risk_decision(quantity=1)
    decision.reason_code = "TRADE_MANAGEMENT_ADD"

    result = engine.execute_trade(decision)

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1


def test_p5_recovery_failure_still_blocks_before_capital_reservation() -> None:
    provider = _CapitalGateProvider(available_funds=10_000.0, buying_power=10_000.0)
    engine = _engine(provider)
    engine.startup_recovery_state = RecoveryState.RECOVERY_FAILED
    engine.startup_recovery_result = StartupRecoveryResult(
        state=RecoveryState.RECOVERY_FAILED,
        reason="unit_test_recovery_failed",
    )

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale == "STARTUP_RECOVERY_NOT_COMPLETE:unit_test_recovery_failed"
    assert provider.submitted_orders == []
    assert engine.capital_authority.active_reservations == {}


def test_failed_order_with_retry_actually_enqueued_keeps_reservation() -> None:
    provider = _RetryFlagProvider(next_retry_tick=1)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1, trader_type="SCALPER"))

    assert result.retry_scheduled is True
    assert engine.pending_book.count() == 1
    assert engine.capital_authority.total_reserved_capital > 0.0


def test_failed_order_with_retry_flag_but_max_attempts_exceeded_releases_reservation() -> None:
    provider = _RetryFlagProvider(next_retry_tick=1)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.retry_scheduled is True
    assert engine.pending_book.count() == 0
    assert engine.capital_authority.active_reservations == {}


def test_failed_order_with_retry_flag_but_execution_disabled_releases_reservation() -> None:
    provider = _RetryFlagProvider(next_retry_tick=1)
    engine = _engine(provider)
    provider.engine_to_disable = engine

    result = engine.execute_trade(_risk_decision(quantity=1, trader_type="SCALPER"))

    assert result.retry_scheduled is True
    assert engine.pending_book.count() == 0
    assert engine.capital_authority.active_reservations == {}


def test_ordinary_rejection_and_cancel_still_release_reservation() -> None:
    rejected_provider = _RetryFlagProvider(status="REJECTED", retry_scheduled=False, next_retry_tick=None)
    rejected_engine = _engine(rejected_provider)

    rejected = rejected_engine.execute_trade(_risk_decision(quantity=1))

    assert rejected.status == "BLOCKED"
    assert rejected_engine.pending_book.count() == 0
    assert rejected_engine.capital_authority.active_reservations == {}

    cancelled_provider = _RetryFlagProvider(status="Cancelled", retry_scheduled=False, next_retry_tick=None)
    cancelled_engine = _engine(cancelled_provider)

    cancelled = cancelled_engine.execute_trade(_risk_decision(quantity=1))

    assert cancelled.status == "BLOCKED"
    assert cancelled_engine.pending_book.count() == 0
    assert cancelled_engine.capital_authority.active_reservations == {}
