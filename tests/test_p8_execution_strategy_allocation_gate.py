from __future__ import annotations

from decimal import Decimal

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.capital_management_authority import CapitalManagementAuthority
from src.core.event_collector import EventCollector
from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import OrderSnapshot, PositionSnapshot
from src.execution.post_fill_lifecycle_engine import (
    ManagedTradeLifecycle,
    PositionLifecycleState,
)
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
            "LIFECYCLE_MAX_POSITION_EXPOSURE": 2_000.0,
            "LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 10_000.0,
            "RISK_MAX_TOTAL_EXPOSURE_PCT": 100.0,
            "STRATEGY_CAPITAL_DEFAULT_ALLOCATION_PCT": 1.0,
        }
    )
    yield
    set_config_overrides(None)


class _P8Provider:
    def __init__(
        self,
        *,
        available_funds: float = 10_000.0,
        buying_power: float = 10_000.0,
        status: str = "Filled",
        filled_quantity: int | None = None,
        retry_scheduled: bool = False,
        next_retry_tick: int | None = None,
    ) -> None:
        self.available_funds = available_funds
        self.buying_power = buying_power
        self.status = status
        self.filled_quantity = filled_quantity
        self.retry_scheduled = retry_scheduled
        self.next_retry_tick = next_retry_tick
        self.submitted_orders: list[object] = []
        self.protective_orders: list[OrderSnapshot] = []

    def name(self) -> str:
        return "P8_STRATEGY_ALLOC_TEST_PROVIDER"

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
        filled = request.quantity if self.filled_quantity is None and self.status == "Filled" else int(self.filled_quantity or 0)
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=self.status == "Filled",
            status=self.status,
            rationale=self.status,
            direction=request.direction,
            quantity=filled,
            requested_quantity=request.quantity,
            filled_quantity=filled,
            remaining_quantity=max(0, request.quantity - filled),
            fill_status="FULL" if filled == request.quantity else "NONE",
            average_fill_price=Decimal("100.00") if filled > 0 else None,
            client_order_id=request.client_order_id,
            ibkr_order_id=1001,
            attempt_number=request.attempt_number,
            retry_scheduled=self.retry_scheduled,
            next_retry_tick=self.next_retry_tick,
            rejection_reason=self.status,
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


def _risk_decision(
    *,
    quantity: int = 1,
    trader_type: str = "P8_TEST",
    symbol: str = "AAPL",
) -> RiskDecision:
    decision = RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=quantity,
        risk_level="LOW",
        rationale="p8 strategy allocation gate",
        trader_type=trader_type,
        strategy_name="unit_strategy",
        direction="BUY",
        stop_loss_price=99.0,
        decision_id=f"risk-p8-{quantity}-{trader_type}",
        intent_id=f"intent-p8-{quantity}-{trader_type}",
    )
    decision.entry_price = 100.0
    return decision


def _strategy_authority(
    limits: dict[str, dict] | None = None,
) -> StrategyCapitalAllocationAuthority:
    return StrategyCapitalAllocationAuthority(
        run_mode="LIVE",
        strategy_limits=limits
        or {
            "UNIT_STRATEGY": {
                "enabled": True,
                "allocation_pct": 1.0,
                "max_positions": 5,
            }
        },
    )


def _engine(
    provider: _P8Provider,
    *,
    strategy_authority: StrategyCapitalAllocationAuthority | None = None,
    capital_authority: CapitalManagementAuthority | None = None,
    trade_registry: ActiveTradeRegistry | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        provider=provider,
        trade_registry=trade_registry or ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        capital_authority=capital_authority,
        strategy_allocation_authority=strategy_authority or _strategy_authority(),
    )


def _max_one_strategy_authority() -> StrategyCapitalAllocationAuthority:
    return _strategy_authority(
        {
            "UNIT_STRATEGY": {
                "enabled": True,
                "allocation_pct": 1.0,
                "max_positions": 1,
            }
        }
    )


def _seed_post_fill_lifecycle_open_trade(
    engine: ExecutionEngine,
    *,
    symbol: str = "AAPL",
    strategy_id: str = "unit_strategy",
    quantity: int = 1,
    price: float = 100.0,
) -> None:
    trade_id = f"seed-{symbol.lower()}"
    engine.post_fill_lifecycle._trades[trade_id] = ManagedTradeLifecycle(
        trade_id=trade_id,
        symbol=symbol.upper(),
        strategy_id=strategy_id,
        side="BUY",
        run_mode="LIVE",
        session_label="LIVE",
        intended_qty=quantity,
        filled_qty=quantity,
        avg_fill_price=price,
        state=PositionLifecycleState.PROTECTED,
    )


def test_p8_blocks_before_p7_capital_reservation() -> None:
    provider = _P8Provider()
    engine = _engine(
        provider,
        strategy_authority=_strategy_authority({"UNIT_STRATEGY": {"enabled": False, "allocation_pct": 1.0}}),
    )

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("STRATEGY_ALLOC_STRATEGY_DISABLED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_p8_allocation_exceeded_blocks_before_p7() -> None:
    provider = _P8Provider()
    engine = _engine(
        provider,
        strategy_authority=_strategy_authority(
            {
                "UNIT_STRATEGY": {
                    "enabled": True,
                    "allocation_pct": 0.01,
                    "max_positions": 5,
                }
            }
        ),
    )

    result = engine.execute_trade(_risk_decision(quantity=2))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("STRATEGY_ALLOC_STRATEGY_CAPITAL_EXCEEDED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_p7_account_capital_rejection_after_p8_approval_releases_strategy_reservation() -> None:
    provider = _P8Provider(available_funds=5.0, buying_power=5.0)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_INSUFFICIENT_CAPITAL")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_p7_limit_rejection_after_p8_approval_releases_strategy_reservation() -> None:
    provider = _P8Provider()
    engine = _engine(provider)
    decision = _risk_decision(quantity=1)
    decision.evaluated_limits = {"max_position_notional": 50.0}

    result = engine.execute_trade(decision)

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_EXPOSURE_LIMIT_EXCEEDED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_force_execute_cannot_bypass_p8_allocation_gate() -> None:
    provider = _P8Provider()
    engine = _engine(
        provider,
        strategy_authority=_strategy_authority(
            {
                "UNIT_STRATEGY": {
                    "enabled": True,
                    "allocation_pct": 0.01,
                    "max_positions": 5,
                }
            }
        ),
    )
    decision = _risk_decision(quantity=2)
    decision.force_execute = True

    result = engine.execute_trade(decision)

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("STRATEGY_ALLOC_STRATEGY_CAPITAL_EXCEEDED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_force_execute_cannot_bypass_p7_after_p8_approval() -> None:
    provider = _P8Provider(available_funds=5.0, buying_power=5.0)
    engine = _engine(provider)
    decision = _risk_decision(quantity=1)
    decision.force_execute = True

    result = engine.execute_trade(decision)

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_INSUFFICIENT_CAPITAL")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_new_buy_at_strategy_max_positions_rejects_when_symbol_not_open() -> None:
    provider = _P8Provider()
    engine = _engine(provider, strategy_authority=_max_one_strategy_authority())
    _seed_post_fill_lifecycle_open_trade(engine, symbol="MSFT")

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("STRATEGY_ALLOC_STRATEGY_POSITION_LIMIT_EXCEEDED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_add_uses_builtin_post_fill_lifecycle_symbol_for_strategy_slot_check() -> None:
    provider = _P8Provider()
    engine = _engine(provider, strategy_authority=_max_one_strategy_authority())
    _seed_post_fill_lifecycle_open_trade(engine, symbol="AAPL")

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1
    assert engine.strategy_allocation_authority.active_reservations == {}


def test_add_from_builtin_post_fill_lifecycle_still_reaches_p7_capital_gate() -> None:
    provider = _P8Provider(available_funds=5.0, buying_power=5.0)
    engine = _engine(provider, strategy_authority=_max_one_strategy_authority())
    _seed_post_fill_lifecycle_open_trade(engine, symbol="AAPL")

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("CAPITAL_INSUFFICIENT_CAPITAL")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_active_trade_registry_fallback_still_allows_add_when_lifecycle_sources_absent() -> None:
    provider = _P8Provider()
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="P8_TEST",
            entry_tick=1,
            entry_price=100.0,
            direction="BUY",
            quantity=1,
            strategy_name="unit_strategy",
            stop_loss_price=99.0,
        )
    )
    engine = _engine(
        provider,
        strategy_authority=_max_one_strategy_authority(),
        trade_registry=registry,
    )
    decision = _risk_decision(quantity=1)
    decision.reason_code = "TRADE_MANAGEMENT_ADD"

    result = engine.execute_trade(decision)

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1
    assert provider.submitted_orders[0].symbol == "AAPL"
    assert provider.submitted_orders[0].strategy_name == "unit_strategy"
    assert engine.strategy_allocation_authority.active_reservations == {}


def test_active_trade_registry_fallback_blocks_ordinary_duplicate_buy() -> None:
    provider = _P8Provider()
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="P8_TEST",
            entry_tick=1,
            entry_price=100.0,
            direction="BUY",
            quantity=1,
            strategy_name="unit_strategy",
            stop_loss_price=99.0,
        )
    )
    engine = _engine(
        provider,
        strategy_authority=_max_one_strategy_authority(),
        trade_registry=registry,
    )

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert result.rationale == "DUPLICATE_POSITION_CONFLICT"
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_active_trade_registry_fallback_blocks_new_symbol_at_strategy_max_positions() -> None:
    provider = _P8Provider()
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="P8_TEST",
            entry_tick=1,
            entry_price=100.0,
            direction="BUY",
            quantity=1,
            strategy_name="unit_strategy",
            stop_loss_price=99.0,
        )
    )
    engine = _engine(
        provider,
        strategy_authority=_max_one_strategy_authority(),
        trade_registry=registry,
    )

    result = engine.execute_trade(_risk_decision(quantity=1, symbol="MSFT"))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("STRATEGY_ALLOC_STRATEGY_POSITION_LIMIT_EXCEEDED")
    assert provider.submitted_orders == []
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_active_trade_registry_fallback_matches_builtin_lifecycle_context_for_existing_symbol() -> None:
    provider = _P8Provider()
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="P8_TEST",
            entry_tick=1,
            entry_price=100.0,
            direction="BUY",
            quantity=1,
            strategy_name="unit_strategy",
            stop_loss_price=99.0,
        )
    )
    registry_engine = _engine(
        provider,
        strategy_authority=_max_one_strategy_authority(),
        trade_registry=registry,
    )
    lifecycle_engine = _engine(_P8Provider(), strategy_authority=_max_one_strategy_authority())
    _seed_post_fill_lifecycle_open_trade(lifecycle_engine, symbol="AAPL")

    registry_context = registry_engine._strategy_allocation_context(_risk_decision(quantity=1))
    lifecycle_context = lifecycle_engine._strategy_allocation_context(_risk_decision(quantity=1))

    assert registry_context["current_symbol_position_exists"] is True
    assert registry_context["current_symbol_position_exists"] == lifecycle_context["current_symbol_position_exists"]
    assert registry_context["current_strategy_open_positions"] == lifecycle_context["current_strategy_open_positions"]
    assert registry_context["current_strategy_exposure"] == lifecycle_context["current_strategy_exposure"]


def test_fill_converts_strategy_reservation_to_exposure() -> None:
    provider = _P8Provider()
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.strategy_allocation_authority.strategy_used_exposure("unit_strategy") == 100.0
    assert engine.capital_authority.symbol_exposure("AAPL") == 100.0


def test_rejected_order_releases_strategy_reservation() -> None:
    provider = _P8Provider(status="REJECTED", filled_quantity=0)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.status == "BLOCKED"
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}


def test_retry_actually_enqueued_keeps_strategy_reservation() -> None:
    provider = _P8Provider(status="Submitted", filled_quantity=0, retry_scheduled=True, next_retry_tick=1)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1, trader_type="SCALPER"))

    assert result.retry_scheduled is True
    assert engine.pending_book.count() == 1
    assert engine.strategy_allocation_authority.strategy_reserved_capital("unit_strategy") == 100.0
    assert engine.capital_authority.total_reserved_capital == 100.0


def test_retry_not_scheduled_releases_strategy_reservation() -> None:
    provider = _P8Provider(status="Submitted", filled_quantity=0, retry_scheduled=True, next_retry_tick=1)
    engine = _engine(provider)

    result = engine.execute_trade(_risk_decision(quantity=1))

    assert result.retry_scheduled is True
    assert engine.pending_book.count() == 0
    assert engine.strategy_allocation_authority.active_reservations == {}
    assert engine.capital_authority.active_reservations == {}
