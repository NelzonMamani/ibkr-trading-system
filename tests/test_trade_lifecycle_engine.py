from datetime import datetime, timedelta, timezone

from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine


def _open_long(engine: TradeLifecycleEngine):
    return engine.open_trade(
        symbol="ELAB",
        side="LONG",
        quantity=10,
        entry_price=10.0,
        stop_price=9.0,
        strategy_name="RossMomentumStrategyV1",
        setup_family_id="setup-a",
        trigger_id="trigger-a",
        execution_mode="FAST_MICRO_PULLBACK",
        execution_primary_timeframe="1m",
        execution_refinement_timeframe="15s",
    )


def test_open_trade_creates_authoritative_state() -> None:
    engine = TradeLifecycleEngine()

    state = _open_long(engine)

    assert state.trade_id
    assert state.status == "OPEN"
    assert state.current_quantity == 10
    assert state.initial_risk_per_share == 1.0
    assert state.lifecycle_events[0].event_type == "OPEN"


def test_mark_to_market_updates_unrealized_pnl_and_r() -> None:
    engine = TradeLifecycleEngine()
    state = _open_long(engine)

    updated = engine.mark_to_market(state.trade_id, current_price=11.0)

    assert updated.unrealized_pnl == 10.0
    assert updated.unrealized_r_multiple == 1.0


def test_add_updates_quantity_and_weighted_average_entry() -> None:
    engine = TradeLifecycleEngine()
    state = _open_long(engine)

    updated = engine.apply_add(state.trade_id, add_quantity=10, add_price=12.0)

    assert updated.current_quantity == 20
    assert round(updated.average_entry_price, 4) == 11.0
    assert updated.add_count == 1


def test_partial_exit_realizes_pnl_without_corrupting_remaining_trade() -> None:
    engine = TradeLifecycleEngine()
    state = _open_long(engine)

    updated = engine.apply_partial_exit(state.trade_id, exit_quantity=4, exit_price=11.0)

    assert updated.realized_pnl == 4.0
    assert updated.current_quantity == 6
    assert updated.average_entry_price == 10.0
    assert updated.status == "PARTIAL"


def test_close_trade_emits_closed_record_with_final_metrics() -> None:
    engine = TradeLifecycleEngine()
    state = _open_long(engine)
    engine.apply_partial_exit(state.trade_id, exit_quantity=5, exit_price=11.0)

    closed = engine.close_trade(state.trade_id, exit_price=12.0, exit_reason="target_hit")

    assert closed.trade_id == state.trade_id
    assert closed.realized_quantity == 10
    assert closed.realized_pnl == 15.0
    assert round(closed.realized_r_multiple, 4) == 1.5
    assert closed.exit_reason == "target_hit"


def test_mfe_and_mae_are_updated_correctly() -> None:
    engine = TradeLifecycleEngine()
    state = _open_long(engine)

    engine.mark_to_market(state.trade_id, current_price=11.5)
    updated = engine.mark_to_market(state.trade_id, current_price=9.2)

    assert round(updated.max_favorable_excursion, 4) == 1.5
    assert round(updated.max_adverse_excursion, 4) == -0.8


def test_short_trade_pnl_signs_are_correct() -> None:
    engine = TradeLifecycleEngine()
    state = engine.open_trade(
        symbol="TSLA",
        side="SHORT",
        quantity=10,
        entry_price=20.0,
        stop_price=21.0,
    )

    marked = engine.mark_to_market(state.trade_id, current_price=19.0)
    assert marked.unrealized_pnl == 10.0
    partial = engine.apply_partial_exit(state.trade_id, exit_quantity=4, exit_price=18.0)

    assert partial.realized_pnl == 8.0


def test_session_summary_metrics_are_correct() -> None:
    engine = TradeLifecycleEngine()
    winner = _open_long(engine)
    loser = engine.open_trade(symbol="ABCD", side="LONG", quantity=5, entry_price=10.0, stop_price=9.0)
    open_state = engine.open_trade(symbol="OPEN", side="LONG", quantity=2, entry_price=10.0, stop_price=9.5)

    engine.close_trade(winner.trade_id, exit_price=11.0, exit_reason="winner")
    engine.close_trade(loser.trade_id, exit_price=9.0, exit_reason="loser")
    engine.mark_to_market(open_state.trade_id, current_price=10.5)

    summary = engine.summarize_session_metrics()

    assert summary["open_trade_count"] == 1.0
    assert summary["closed_trade_count"] == 2.0
    assert summary["winners"] == 1.0
    assert summary["losers"] == 1.0
    assert summary["realized_pnl_total"] == 5.0
    assert summary["unrealized_pnl_total"] == 1.0
    assert summary["win_rate"] == 0.5


def test_logs_emit_required_lifecycle_markers(capsys) -> None:
    engine = TradeLifecycleEngine()
    state = engine.open_trade(symbol="LOG", side="LONG", quantity=1, entry_price=10.0, stop_price=9.0)
    engine.apply_add(state.trade_id, add_quantity=1, add_price=10.5)
    engine.apply_partial_exit(state.trade_id, exit_quantity=1, exit_price=11.0)
    engine.move_stop(state.trade_id, stop_price=10.2)
    engine.mark_to_market(state.trade_id, current_price=10.8)
    engine.close_trade(state.trade_id, exit_price=10.7, exit_reason="manual")
    engine.summarize_session_metrics()

    output = capsys.readouterr().out
    for marker in [
        "[TRADE][OPEN]",
        "[TRADE][ADD]",
        "[TRADE][PARTIAL]",
        "[TRADE][STOP_MOVE]",
        "[TRADE][MARK]",
        "[TRADE][CLOSE]",
        "[TRADE][SUMMARY]",
    ]:
        assert marker in output


def test_close_holding_time_is_deterministic() -> None:
    engine = TradeLifecycleEngine()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(seconds=90)
    state = engine.open_trade(
        symbol="TIME",
        side="LONG",
        quantity=1,
        entry_price=10.0,
        stop_price=9.0,
        timestamp=start,
    )

    closed = engine.close_trade(state.trade_id, exit_price=10.0, exit_reason="time", timestamp=end)

    assert closed.holding_time_seconds == 90
