from src.core.engines.position_management_engine import ManagedPosition, PositionManagementEngine


def _position(mode: str = "NORMAL") -> ManagedPosition:
    return ManagedPosition(
        symbol="ABCD",
        side="LONG",
        quantity=100,
        entry_price=10.0,
        stop_price=9.0,
        execution_mode=mode,
        timeframe="1m",
    )


def test_add_only_on_winner_and_structure_confirmation() -> None:
    engine = PositionManagementEngine()
    position = _position()

    updated = engine.manage_position(
        position,
        {
            "current_price": 10.6,
            "breaks_new_level": True,
            "pullback_holds_support": False,
        },
    )

    assert updated.quantity == 125
    assert updated.add_count == 1


def test_partials_and_break_even_trailing() -> None:
    engine = PositionManagementEngine()
    position = _position()

    updated = engine.manage_position(
        position,
        {
            "current_price": 12.0,
            "higher_low": 11.5,
        },
    )

    # +2R hits both partial targets: 50 + 25 shares off initial 100.
    assert updated.quantity == 25
    assert updated.partials_taken == {"1R", "2R"}
    # Structure trail should lift stop above break-even.
    assert updated.stop_price > updated.entry_price


def test_failure_exit_for_momentum_vwap_loss() -> None:
    engine = PositionManagementEngine()
    position = _position(mode="FAST_MICRO_PULLBACK")

    updated = engine.manage_position(
        position,
        {
            "current_price": 10.7,
            "vwap_lost": True,
        },
    )

    assert updated.closed is True
    assert updated.quantity == 0
    assert updated.exit_reason == "vwap_loss"


def test_no_average_down_when_price_below_entry() -> None:
    engine = PositionManagementEngine()
    position = _position()

    updated = engine.manage_position(
        position,
        {
            "current_price": 9.8,
            "breaks_new_level": True,
            "pullback_holds_support": True,
        },
    )

    assert updated.quantity == 100
    assert updated.add_count == 0
