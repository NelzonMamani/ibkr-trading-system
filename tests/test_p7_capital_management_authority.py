from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from src.config.config_resolver import set_config_overrides
from src.core.capital_management_authority import (
    CapitalDecisionStatus,
    CapitalManagementAuthority,
)
from src.storage.sqlite_store import SQLiteStore


@pytest.fixture(autouse=True)
def _reset_config() -> None:
    set_config_overrides(
        {
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


def _decision(
    authority: CapitalManagementAuthority,
    *,
    run_mode: str = "PAPER",
    quantity: int = 5,
    price: float = 100.0,
    available: float | None = 1_000.0,
    buying_power: float | None = 1_000.0,
    equity: float | None = 10_000.0,
    current_total: float = 0.0,
    current_symbol: float = 0.0,
    current_positions: int = 0,
    current_symbol_position_exists: bool = False,
    max_positions: int | None = None,
    max_position_notional: float | None = None,
    max_total_exposure: float | None = None,
    max_symbol_exposure: float | None = None,
    reserve: bool = True,
):
    return authority.evaluate_entry(
        run_mode=run_mode,
        strategy_id="unit_strategy",
        symbol="AAPL",
        side="BUY",
        requested_quantity=quantity,
        reference_price=price,
        account_equity=equity,
        available_capital=available,
        buying_power=buying_power,
        current_total_exposure=current_total,
        current_symbol_exposure=current_symbol,
        current_open_positions=current_positions,
        current_symbol_position_exists=current_symbol_position_exists,
        max_open_positions=max_positions,
        max_position_notional=max_position_notional,
        max_total_exposure=max_total_exposure,
        max_symbol_exposure=max_symbol_exposure,
        broker_truth_available=run_mode == "LIVE" if available is not None else None,
        intent_id="intent-aapl",
        reserve=reserve,
    )


def test_sim_and_paper_capital_approvals_use_deterministic_configured_capital(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_DEFAULT_CAPITAL", "500")
    sim_authority = CapitalManagementAuthority(run_mode="SIM")
    sim = sim_authority.evaluate_entry(
        run_mode="SIM",
        strategy_id="unit_strategy",
        symbol="AAPL",
        side="BUY",
        requested_quantity=3,
        reference_price=100.0,
        current_open_positions=0,
        intent_id="intent-sim",
    )
    paper = CapitalManagementAuthority(run_mode="PAPER").evaluate_entry(
        run_mode="PAPER",
        strategy_id="unit_strategy",
        symbol="AAPL",
        side="BUY",
        requested_quantity=3,
        reference_price=100.0,
        current_open_positions=0,
        intent_id="intent-paper",
    )

    assert sim.status == CapitalDecisionStatus.APPROVED
    assert paper.status == CapitalDecisionStatus.APPROVED
    assert sim.available_capital == 500.0
    assert paper.available_capital == 500.0


def test_read_only_and_live_missing_truth_fail_closed_without_reservation() -> None:
    read_only = _decision(CapitalManagementAuthority(run_mode="READ_ONLY"), run_mode="READ_ONLY")
    live_missing = CapitalManagementAuthority(run_mode="LIVE").evaluate_entry(
        run_mode="LIVE",
        strategy_id="unit_strategy",
        symbol="AAPL",
        side="BUY",
        requested_quantity=1,
        reference_price=100.0,
        current_open_positions=0,
    )

    assert read_only.status == CapitalDecisionStatus.READ_ONLY_BLOCKED
    assert read_only.executable is False
    assert live_missing.status == CapitalDecisionStatus.DATA_UNAVAILABLE
    assert live_missing.executable is False


def test_insufficient_capital_rejects_and_no_reservation_is_created() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    decision = _decision(authority, available=50.0, buying_power=50.0, quantity=1, price=100.0)

    assert decision.status == CapitalDecisionStatus.INSUFFICIENT_CAPITAL
    assert authority.active_reservations == {}


def test_max_open_positions_rejects() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    decision = _decision(authority, current_positions=5, max_positions=5)

    assert decision.status == CapitalDecisionStatus.MAX_POSITIONS_EXCEEDED
    assert decision.reason == "MAX_POSITIONS_EXCEEDED"


def test_max_open_positions_does_not_reject_add_to_existing_symbol() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    decision = _decision(
        authority,
        quantity=1,
        current_positions=5,
        current_symbol=500.0,
        current_symbol_position_exists=True,
        max_positions=5,
        max_symbol_exposure=2_000.0,
    )

    assert decision.status == CapitalDecisionStatus.APPROVED
    assert decision.reason == "CAPITAL_APPROVED"


def test_add_to_existing_symbol_still_obeys_exposure_and_capital_limits() -> None:
    exposure_limited = CapitalManagementAuthority(run_mode="PAPER")
    exposure_decision = _decision(
        exposure_limited,
        quantity=1,
        current_positions=5,
        current_symbol=950.0,
        current_symbol_position_exists=True,
        max_positions=5,
        max_symbol_exposure=1_000.0,
    )
    capital_limited = CapitalManagementAuthority(run_mode="PAPER")
    capital_decision = _decision(
        capital_limited,
        quantity=1,
        available=50.0,
        buying_power=50.0,
        current_positions=5,
        current_symbol=500.0,
        current_symbol_position_exists=True,
        max_positions=5,
        max_symbol_exposure=2_000.0,
    )

    assert exposure_decision.status == CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED
    assert exposure_decision.reason == "SYMBOL_EXPOSURE_LIMIT_EXCEEDED"
    assert capital_decision.status == CapitalDecisionStatus.INSUFFICIENT_CAPITAL
    assert capital_limited.active_reservations == {}


def test_position_total_and_symbol_exposure_limits_reject() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    too_large_position = _decision(authority, quantity=11, price=100.0, max_position_notional=1_000.0)
    total_exposure = _decision(
        authority,
        quantity=2,
        price=100.0,
        current_total=950.0,
        max_total_exposure=1_000.0,
    )
    symbol_exposure = _decision(
        authority,
        quantity=2,
        price=100.0,
        current_symbol=950.0,
        max_symbol_exposure=1_000.0,
    )

    assert too_large_position.status == CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED
    assert too_large_position.reason == "MAX_POSITION_NOTIONAL_EXCEEDED"
    assert total_exposure.status == CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED
    assert total_exposure.reason == "TOTAL_EXPOSURE_LIMIT_EXCEEDED"
    assert symbol_exposure.status == CapitalDecisionStatus.EXPOSURE_LIMIT_EXCEEDED
    assert symbol_exposure.reason == "SYMBOL_EXPOSURE_LIMIT_EXCEEDED"


def test_approved_or_reduced_decision_creates_reservation_only_when_executable() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    approved = _decision(authority, quantity=5, price=100.0, max_symbol_exposure=2_000.0)
    reduced = _decision(
        authority,
        quantity=8,
        price=100.0,
        available=650.0,
        buying_power=650.0,
        max_symbol_exposure=2_000.0,
    )
    rejected = _decision(
        authority,
        quantity=1,
        price=100.0,
        available=50.0,
        buying_power=50.0,
        max_symbol_exposure=2_000.0,
    )

    assert approved.status == CapitalDecisionStatus.APPROVED
    assert reduced.status == CapitalDecisionStatus.REDUCED
    assert reduced.approved_quantity == 6
    assert rejected.status == CapitalDecisionStatus.INSUFFICIENT_CAPITAL
    assert len(authority.active_reservations) == 2
    assert rejected.decision_id not in {r.decision_id for r in authority.active_reservations.values()}


def test_cancelled_and_rejected_orders_release_reservations() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    cancelled = _decision(authority, quantity=1, price=100.0)
    rejected = _decision(authority, quantity=1, price=100.0)
    authority.attach_order(decision_id=cancelled.decision_id, order_id="ORDER-CANCEL")
    authority.attach_order(decision_id=rejected.decision_id, order_id="ORDER-REJECT")

    authority.release_reservation(order_id="ORDER-CANCEL", reason="ORDER_CANCELLED")
    authority.release_reservation(order_id="ORDER-REJECT", reason="ORDER_REJECTED")

    assert authority.total_reserved_capital == 0.0
    assert authority.active_reservations == {}


def test_partial_and_full_fill_convert_reservation_to_exposure_and_clear_active_slice() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    decision = _decision(authority, quantity=5, price=100.0)
    authority.attach_order(decision_id=decision.decision_id, order_id="ORDER-FILL")

    authority.convert_reservation_to_exposure(
        decision_id=decision.decision_id,
        order_id="ORDER-FILL",
        symbol="AAPL",
        strategy_id="unit_strategy",
        fill_quantity=2,
        fill_price=100.0,
        trade_id="TRADE-1",
    )
    reservation = next(iter(authority.active_reservations.values()))
    assert reservation.remaining_quantity == 3
    assert authority.symbol_exposure("AAPL") == 200.0

    authority.convert_reservation_to_exposure(
        decision_id=decision.decision_id,
        order_id="ORDER-FILL",
        symbol="AAPL",
        strategy_id="unit_strategy",
        fill_quantity=3,
        fill_price=100.0,
        trade_id="TRADE-1",
    )

    assert authority.symbol_exposure("AAPL") == 500.0
    assert authority.active_reservations == {}


def test_full_exit_releases_used_exposure() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    decision = _decision(authority, quantity=5, price=100.0)
    authority.attach_order(decision_id=decision.decision_id, order_id="ORDER-FILL")
    authority.convert_reservation_to_exposure(
        decision_id=decision.decision_id,
        order_id="ORDER-FILL",
        symbol="AAPL",
        strategy_id="unit_strategy",
        fill_quantity=5,
        fill_price=100.0,
        trade_id="TRADE-1",
    )

    released = authority.release_exposure(symbol="AAPL", quantity=5, price=100.0, strategy_id="unit_strategy")

    assert released == 500.0
    assert authority.total_used_exposure == 0.0


def test_restart_recovery_rebuilds_lifecycle_exposure_and_open_order_reservation() -> None:
    authority = CapitalManagementAuthority(run_mode="PAPER")
    lifecycle_trade = SimpleNamespace(
        lifecycle_trade_id="LIFE-1",
        symbol="AAPL",
        strategy_name="unit_strategy",
        quantity_open=5,
        entry_avg_price=100.0,
    )
    open_entry = SimpleNamespace(
        order_id="ENTRY-1",
        symbol="MSFT",
        status="Submitted",
        order_type="LMT",
        metadata={
            "side": "BUY",
            "quantity": 2,
            "limit_price": 50.0,
            "capital_decision_id": "cap-existing",
            "strategy_id": "unit_strategy",
        },
    )
    already_filled_trade_order = SimpleNamespace(
        order_id="ENTRY-OLD",
        symbol="AAPL",
        status="Submitted",
        order_type="LMT",
        metadata={"side": "BUY", "quantity": 5, "limit_price": 100.0, "trade_id": "LIFE-1"},
    )

    authority.recover_from_lifecycle([lifecycle_trade])
    recovered_orders = authority.recover_from_open_orders([open_entry, already_filled_trade_order])

    assert authority.symbol_exposure("AAPL") == 500.0
    assert recovered_orders == 1
    assert authority.total_reserved_capital == 100.0


def test_storage_audit_records_capital_decision_and_reservation(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "capital.db"))
    store.initialize_schema()
    authority = CapitalManagementAuthority(run_mode="PAPER", storage_engine=store)

    decision = _decision(authority, quantity=1, price=100.0)

    rows = store.connection.execute("SELECT * FROM capital_audit_events WHERE decision_id = ?", (decision.decision_id,)).fetchall()
    assert {row["event_type"] for row in rows} == {"DECISION", "RESERVED"}
    assert rows[0]["symbol"] == "AAPL"
    store.close()
