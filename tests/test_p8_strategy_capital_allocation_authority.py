from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.strategy_capital_allocation_authority import (
    StrategyAllocationStatus,
    StrategyCapitalAllocationAuthority,
)


@pytest.fixture(autouse=True)
def _reset_config() -> None:
    set_config_overrides(
        {
            "STRATEGY_CAPITAL_ALLOCATIONS": {},
            "STRATEGY_CAPITAL_DEFAULT_ALLOCATION_PCT": 0.50,
            "TRADING_DEFAULT_CAPITAL": 1_000.0,
        }
    )
    yield
    set_config_overrides(None)


def _authority(
    limits: dict[str, dict] | None = None,
) -> StrategyCapitalAllocationAuthority:
    return StrategyCapitalAllocationAuthority(
        run_mode="PAPER",
        strategy_limits=limits
        or {
            "UNIT_STRATEGY": {
                "enabled": True,
                "allocation_pct": 0.50,
                "max_positions": 2,
            }
        },
    )


def _decision(
    authority: StrategyCapitalAllocationAuthority,
    *,
    run_mode: str = "PAPER",
    strategy_id: str = "unit_strategy",
    quantity: int = 4,
    price: float = 100.0,
    available_capital: float | None = 1_000.0,
    current_strategy_exposure: float = 0.0,
    current_strategy_open_positions: int = 0,
    current_symbol_position_exists: bool = False,
    daily_count: int = 0,
    recovery_complete: bool = True,
    broker_truth_available: bool = True,
):
    return authority.evaluate_entry(
        run_mode=run_mode,
        strategy_id=strategy_id,
        symbol="AAPL",
        side="BUY",
        requested_quantity=quantity,
        reference_price=price,
        available_capital=available_capital,
        account_equity=available_capital,
        current_strategy_exposure=current_strategy_exposure,
        current_strategy_open_positions=current_strategy_open_positions,
        current_symbol_position_exists=current_symbol_position_exists,
        strategy_daily_trade_count=daily_count,
        recovery_complete=recovery_complete,
        broker_truth_available=broker_truth_available,
        intent_id="intent-p8",
    )


def test_disabled_strategy_rejects_without_reservation() -> None:
    authority = _authority({"UNIT_STRATEGY": {"enabled": False, "allocation_pct": 0.50}})

    decision = _decision(authority)

    assert decision.status == StrategyAllocationStatus.STRATEGY_DISABLED
    assert decision.reason == "STRATEGY_DISABLED"
    assert authority.active_reservations == {}


def test_enabled_strategy_approves_within_allocation() -> None:
    authority = _authority()

    decision = _decision(authority, quantity=4)

    assert decision.status == StrategyAllocationStatus.APPROVED
    assert decision.approved_quantity == 4
    assert decision.strategy_capital_limit == 500.0
    assert authority.strategy_reserved_capital("unit_strategy") == 400.0


def test_strategy_capital_cap_rejects() -> None:
    authority = _authority()

    decision = _decision(authority, quantity=6)

    assert decision.status == StrategyAllocationStatus.STRATEGY_CAPITAL_EXCEEDED
    assert decision.reason == "STRATEGY_CAPITAL_EXCEEDED"
    assert authority.active_reservations == {}


def test_strategy_capital_cap_reduces_when_configured() -> None:
    authority = _authority(
        {
            "UNIT_STRATEGY": {
                "enabled": True,
                "allocation_pct": 0.50,
                "max_positions": 2,
                "allow_reduction": True,
            }
        }
    )

    decision = _decision(authority, quantity=6)

    assert decision.status == StrategyAllocationStatus.REDUCED
    assert decision.approved_quantity == 5
    assert decision.approved_notional == 500.0
    assert authority.strategy_reserved_capital("unit_strategy") == 500.0


def test_strategy_max_open_positions_rejects_new_position() -> None:
    authority = _authority({"UNIT_STRATEGY": {"enabled": True, "allocation_pct": 0.80, "max_positions": 1}})

    decision = _decision(authority, quantity=1, current_strategy_open_positions=1)

    assert decision.status == StrategyAllocationStatus.STRATEGY_POSITION_LIMIT_EXCEEDED
    assert authority.active_reservations == {}


def test_add_to_existing_symbol_does_not_consume_new_strategy_slot() -> None:
    authority = _authority({"UNIT_STRATEGY": {"enabled": True, "allocation_pct": 0.80, "max_positions": 1}})

    decision = _decision(
        authority,
        quantity=1,
        current_strategy_open_positions=1,
        current_symbol_position_exists=True,
    )

    assert decision.status == StrategyAllocationStatus.APPROVED


def test_strategy_daily_trade_limit_rejects_when_configured() -> None:
    authority = _authority(
        {
            "UNIT_STRATEGY": {
                "enabled": True,
                "allocation_pct": 0.80,
                "max_positions": 2,
                "max_daily_trades": 1,
            }
        }
    )

    decision = _decision(authority, quantity=1, daily_count=1)

    assert decision.status == StrategyAllocationStatus.STRATEGY_TRADE_LIMIT_EXCEEDED


def test_read_only_blocks_executable_allocation() -> None:
    authority = _authority()

    decision = _decision(authority, run_mode="READ_ONLY", quantity=1)

    assert decision.status == StrategyAllocationStatus.READ_ONLY_BLOCKED
    assert decision.executable is False
    assert authority.active_reservations == {}


def test_recovery_pending_blocks_allocation() -> None:
    authority = _authority()

    decision = _decision(authority, quantity=1, recovery_complete=False)

    assert decision.status == StrategyAllocationStatus.RECOVERY_NOT_COMPLETE
    assert authority.active_reservations == {}


def test_live_missing_truth_blocks_allocation() -> None:
    authority = _authority()

    decision = _decision(
        authority,
        run_mode="LIVE",
        quantity=1,
        available_capital=None,
        broker_truth_available=False,
    )

    assert decision.status == StrategyAllocationStatus.CAPITAL_UNAVAILABLE
    assert authority.active_reservations == {}


def test_rejection_release_fill_conversion_and_exit_release() -> None:
    authority = _authority({"UNIT_STRATEGY": {"enabled": True, "allocation_pct": 1.0, "max_positions": 2}})
    decision = _decision(authority, quantity=5)
    reservation = next(iter(authority.active_reservations.values()))
    authority.attach_order(decision_id=decision.decision_id, order_id="order-1")

    authority.convert_reservation_to_exposure(
        decision_id=decision.decision_id,
        order_id="order-1",
        strategy_id="unit_strategy",
        symbol="AAPL",
        fill_quantity=2,
        fill_price=100.0,
        trade_id="trade-1",
    )
    assert reservation.remaining_quantity == 3
    assert reservation.remaining_notional == 300.0
    assert authority.strategy_used_exposure("unit_strategy") == 200.0

    authority.convert_reservation_to_exposure(
        decision_id=decision.decision_id,
        order_id="order-1",
        strategy_id="unit_strategy",
        symbol="AAPL",
        fill_quantity=3,
        fill_price=100.0,
        trade_id="trade-1",
    )
    assert authority.active_reservations == {}
    assert authority.strategy_used_exposure("unit_strategy") == 500.0

    released = authority.release_exposure(
        strategy_id="unit_strategy",
        quantity=5,
        price=100.0,
        reason="EXIT_FILL",
    )
    assert released == 500.0
    assert authority.strategy_used_exposure("unit_strategy") == 0.0


def test_release_reservation_on_rejection() -> None:
    authority = _authority()
    decision = _decision(authority, quantity=1)

    released = authority.release_reservation(decision_id=decision.decision_id, reason="ORDER_REJECTED")

    assert released == 100.0
    assert authority.active_reservations == {}


def test_restart_recovery_rebuilds_per_strategy_usage() -> None:
    authority = _authority()
    trades = [
        SimpleNamespace(strategy_name="unit_strategy", quantity_open=2, entry_avg_price=100.0),
        SimpleNamespace(strategy_name="other_strategy", quantity_open=1, entry_avg_price=50.0),
    ]

    recovered = authority.recover_from_lifecycle(trades)

    assert recovered == 2
    assert authority.strategy_used_exposure("unit_strategy") == 200.0
    assert authority.strategy_open_positions("unit_strategy") == 1
    assert authority.strategy_used_exposure("other_strategy") == 50.0


def test_one_strategy_cannot_consume_all_capital_by_default() -> None:
    authority = StrategyCapitalAllocationAuthority(run_mode="PAPER", strategy_limits={})

    decision = _decision(authority, quantity=6)

    assert decision.strategy_capital_limit == 500.0
    assert decision.status == StrategyAllocationStatus.STRATEGY_CAPITAL_EXCEEDED
