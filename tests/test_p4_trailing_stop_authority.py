from src.core.trailing_stop_authority import TrailingStopAuthority, TrailingStopDecisionStatus


def _decision(**overrides):
    params = {
        "symbol": "AAPL",
        "side": "LONG",
        "current_stop_price": 99.0,
        "proposed_stop_price": 100.0,
        "quantity": 3,
        "live_position_quantity": 3,
        "has_active_stop": True,
        "recovery_complete": True,
        "run_mode": "PAPER",
        "trigger_price": 102.0,
        "reference_price": 102.0,
    }
    params.update(overrides)
    return TrailingStopAuthority().evaluate_update(**params)


def test_trailing_stop_blocked_before_initial_protective_stop_exists() -> None:
    decision = _decision(has_active_stop=False)

    assert decision.status == TrailingStopDecisionStatus.BLOCKED
    assert decision.blocked_reason == "INITIAL_PROTECTIVE_STOP_REQUIRED"


def test_long_trailing_update_cannot_loosen_stop() -> None:
    decision = _decision(current_stop_price=100.0, proposed_stop_price=99.5)

    assert decision.status == TrailingStopDecisionStatus.REJECTED
    assert decision.reason == "STOP_LOOSENING_REJECTED"


def test_short_trailing_update_cannot_loosen_stop() -> None:
    decision = _decision(side="SHORT", current_stop_price=101.0, proposed_stop_price=101.5)

    assert decision.status == TrailingStopDecisionStatus.REJECTED
    assert decision.reason == "STOP_LOOSENING_REJECTED"


def test_valid_long_tightening_is_approved() -> None:
    decision = _decision(current_stop_price=99.0, proposed_stop_price=100.0)

    assert decision.status == TrailingStopDecisionStatus.APPROVED
    assert decision.is_tightening is True


def test_valid_short_tightening_is_approved() -> None:
    decision = _decision(
        side="SHORT",
        current_stop_price=101.0,
        proposed_stop_price=100.5,
        trigger_price=99.0,
        reference_price=99.0,
    )

    assert decision.status == TrailingStopDecisionStatus.APPROVED
    assert decision.is_tightening is True


def test_long_stale_high_water_candidate_above_current_price_is_rejected() -> None:
    decision = _decision(
        current_stop_price=100.0,
        proposed_stop_price=109.17,
        trigger_price=102.0,
        reference_price=110.0,
    )

    assert decision.status == TrailingStopDecisionStatus.REJECTED
    assert decision.reason == "STOP_CROSSES_MARKET"


def test_short_stale_low_water_candidate_below_current_price_is_rejected() -> None:
    decision = _decision(
        side="SHORT",
        current_stop_price=100.0,
        proposed_stop_price=95.0,
        trigger_price=98.0,
        reference_price=94.0,
    )

    assert decision.status == TrailingStopDecisionStatus.REJECTED
    assert decision.reason == "STOP_CROSSES_MARKET"


def test_quantity_cannot_exceed_remaining_position_quantity() -> None:
    decision = _decision(quantity=4, live_position_quantity=3)

    assert decision.status == TrailingStopDecisionStatus.REJECTED
    assert decision.reason == "TRAILING_QUANTITY_EXCEEDS_POSITION"


def test_recovery_incomplete_blocks_trailing_update() -> None:
    decision = _decision(recovery_complete=False)

    assert decision.status == TrailingStopDecisionStatus.BLOCKED
    assert decision.blocked_reason == "STARTUP_RECOVERY_NOT_COMPLETE"
