from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.runtime_config import RunMode  # noqa: E402
from config.trading_config import MAX_HOLD_TICKS, MIN_HOLD_TICKS  # noqa: E402
from config.runtime_config import RuntimeConfig  # noqa: E402
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from core.event_collector import EventCollector  # noqa: E402
from execution.trade_exit_engine import TradeExitEngine  # noqa: E402
from sim.price_feed import DeterministicPriceFeed  # noqa: E402
from strategy.exit_signal import ExitSignal  # noqa: E402


def test_trade_exit_engine_enforces_tick_based_exit_window():
    """
    Trades should stay open until the deterministic max hold tick is reached.
    """

    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "ABC"
    trader_type = "SIM_TRADER"
    strategy_name = "TestStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)

    trade_registry.register_trade(
        ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=entry_tick,
            entry_price=entry_price,
            direction="LONG",
            quantity=1,
            strategy_name=strategy_name,
            stop_loss_price=round(entry_price - 0.05, 2),
            take_profit_price=round(entry_price + 100.0, 2),
        )
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    pre_min_tick = entry_tick + max(MIN_HOLD_TICKS - 1, 0)
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=pre_min_tick
    )

    assert results == []
    assert outcomes == []
    assert trade_registry.get_trade(symbol, trader_type) is not None

    mid_tick = entry_tick + MAX_HOLD_TICKS - 1
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=mid_tick
    )

    assert results == []
    assert outcomes == []
    assert trade_registry.get_trade(symbol, trader_type) is not None

    close_tick = entry_tick + MAX_HOLD_TICKS
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=close_tick
    )

    expected_exit_price = price_feed.price_for(symbol, close_tick)

    assert len(results) == 1
    assert len(outcomes) == 1
    assert trade_registry.get_trade(symbol, trader_type) is None

    closed_result = results[0]
    assert closed_result.exit_tick == close_tick
    assert closed_result.exit_price == expected_exit_price
    assert (
        "Exit condition met: maximum hold duration reached"
        in closed_result.rationale
    )

    closed_events = event_collector.filter_by_type("TRADE_CLOSED")
    assert len(closed_events) == 1
    payload = closed_events[0].payload

    assert payload["tick"] == close_tick
    assert payload["hold_duration_ticks"] == MAX_HOLD_TICKS
    assert payload["min_hold_ticks"] == MIN_HOLD_TICKS
    assert payload["max_hold_ticks"] == MAX_HOLD_TICKS
    assert payload["realised_pnl"] == round(
        expected_exit_price - entry_price, 2
    )
    assert (
        "Exit condition met: maximum hold duration reached"
        in payload["reason"]
    )


def test_exit_signal_honoured_after_minimum_hold():
    """
    Strategy exit signals should be honoured once the minimum hold is satisfied.
    """

    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "XYZ"
    trader_type = "SIM_TRADER"
    strategy_name = "GapAndGoStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)

    trade_registry.register_trade(
        ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=entry_tick,
            entry_price=entry_price,
            direction="LONG",
            quantity=1,
            strategy_name=strategy_name,
            stop_loss_price=round(entry_price - 0.05, 2),
        )
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    exit_signal = ExitSignal(
        symbol=symbol,
        trader_type=trader_type,
        strategy_name=strategy_name,
        reason="Strategy requests exit after minimum hold duration.",
    )

    close_tick = entry_tick + MIN_HOLD_TICKS
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=close_tick, exit_signals=[exit_signal]
    )

    assert len(results) == 1
    assert len(outcomes) == 1
    assert trade_registry.get_trade(symbol, trader_type) is None

    closed_result = results[0]
    assert closed_result.exit_tick == close_tick
    assert "Strategy exit request honoured" in closed_result.rationale


def test_exit_signal_ignored_before_minimum_hold():
    """
    Strategy exit signals should not bypass the minimum hold requirement.
    """

    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "LMN"
    trader_type = "SIM_TRADER"
    strategy_name = "MomentumContinuationStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)

    trade_registry.register_trade(
        ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=entry_tick,
            entry_price=entry_price,
            direction="LONG",
            quantity=1,
            strategy_name=strategy_name,
            stop_loss_price=round(entry_price - 0.05, 2),
        )
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    exit_signal = ExitSignal(
        symbol=symbol,
        trader_type=trader_type,
        strategy_name=strategy_name,
        reason="Strategy requests early exit.",
    )

    pre_min_tick = entry_tick + max(MIN_HOLD_TICKS - 1, 0)
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=pre_min_tick, exit_signals=[exit_signal]
    )

    assert results == []
    assert outcomes == []
    assert trade_registry.get_trade(symbol, trader_type) is not None


def test_stop_loss_exit_triggers_even_before_minimum_hold():
    """
    Price-based stop-loss exits should be enforced by the TradeExitEngine immediately.
    """

    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "ABC"
    trader_type = "SIM_TRADER"
    strategy_name = "ProtectiveStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)
    stop_loss_price = entry_price + 0.01

    trade_registry.register_trade(
        ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=entry_tick,
            entry_price=entry_price,
            direction="SHORT",
            quantity=1,
            strategy_name=strategy_name,
            stop_loss_price=stop_loss_price,
            take_profit_price=round(entry_price - 100.0, 2),
        )
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    trigger_tick = entry_tick + 1
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=trigger_tick
    )

    assert len(results) == 1
    assert len(outcomes) == 1
    assert trade_registry.get_trade(symbol, trader_type) is None

    closed_result = results[0]
    assert closed_result.exit_tick == trigger_tick
    assert "failed setup / invalidation" in closed_result.rationale
    assert closed_result.stop_loss_price == stop_loss_price


def test_take_profit_exit_triggers_when_threshold_hit():
    """
    Price-based take-profit exits should be enforced when the threshold is met.
    """

    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "XYZ"
    trader_type = "SIM_TRADER"
    strategy_name = "ProtectiveStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)
    take_profit_price = entry_price + 0.01
    stop_loss_price = round(entry_price - 0.05, 2)

    trade_registry.register_trade(
        ActiveTrade(
            symbol=symbol,
            trader_type=trader_type,
            entry_tick=entry_tick,
            entry_price=entry_price,
            direction="LONG",
            quantity=1,
            strategy_name=strategy_name,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    trigger_tick = entry_tick + 1
    results, outcomes = exit_engine.evaluate_and_close_trades(
        run_mode=RunMode.PAPER, tick=trigger_tick
    )

    assert len(results) == 1
    assert len(outcomes) == 1
    assert trade_registry.get_trade(symbol, trader_type) is None

    closed_result = results[0]
    assert closed_result.exit_tick == trigger_tick
    assert "take-profit price reached" in closed_result.rationale
    assert closed_result.take_profit_price == take_profit_price


def test_exit_precedence_breaker_overrides_stop_and_strategy():
    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "BRK"
    trader_type = "SIM_TRADER"
    strategy_name = "RiskFirstStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)

    trade = ActiveTrade(
        symbol=symbol,
        trader_type=trader_type,
        entry_tick=entry_tick,
        entry_price=entry_price,
        direction="LONG",
        quantity=1,
        strategy_name=strategy_name,
        stop_loss_price=entry_price + 0.01,
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    decision = exit_engine.decide_exit(
        trade=trade,
        current_tick=entry_tick + 1,
        current_price=entry_price - 10.0,
        strategy_exit_signal=True,
        config=RuntimeConfig(min_hold_ticks=0, max_hold_ticks=10),
        breaker_tripped=True,
        risk_exit_signal=True,
    )

    assert decision is not None
    assert decision.category == "EXIT_BREAKER"


def test_exit_precedence_stop_overrides_risk_and_strategy():
    price_feed = DeterministicPriceFeed()
    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    symbol = "STP"
    trader_type = "SIM_TRADER"
    strategy_name = "ProtectiveStrategy"
    entry_tick = 0
    entry_price = price_feed.price_for(symbol, entry_tick)

    trade = ActiveTrade(
        symbol=symbol,
        trader_type=trader_type,
        entry_tick=entry_tick,
        entry_price=entry_price,
        direction="LONG",
        quantity=1,
        strategy_name=strategy_name,
        stop_loss_price=entry_price - 0.01,
    )

    exit_engine = TradeExitEngine(
        trade_registry=trade_registry,
        event_collector=event_collector,
        price_feed=price_feed,
    )

    decision = exit_engine.decide_exit(
        trade=trade,
        current_tick=entry_tick + 1,
        current_price=entry_price - 1.0,
        strategy_exit_signal=True,
        config=RuntimeConfig(min_hold_ticks=0, max_hold_ticks=10),
        breaker_tripped=False,
        risk_exit_signal=True,
    )

    assert decision is not None
    assert decision.category in {"EXIT_STOP_LOSS", "EXIT_FAILED_SETUP"}


# The shutdown authority is produced by canonical Core; legacy imports above
# intentionally retain their existing enum aliases and test semantics.
from copy import deepcopy  # noqa: E402
from dataclasses import asdict  # noqa: E402

import pytest  # noqa: E402

from src.config.runtime_config import RunMode as ShutdownRunMode  # noqa: E402
from execution.trade_exit_engine import ShutdownExecutionContext  # noqa: E402


class _ShutdownPriceBoundary:
    def __init__(self, *, allowed=False):
        self.allowed = allowed
        self.calls = []

    def price_for(self, symbol, tick):
        self.calls.append((symbol, tick))
        if not self.allowed:
            raise AssertionError("Shutdown cannot invent a native execution price")
        return 10.75


def _shutdown_owner(*, allow_price=False, open_trade=True):
    """Existing TradeExit/registry/event owners only; no Core or provider I/O."""
    registry = ActiveTradeRegistry()
    events = EventCollector()
    feed = _ShutdownPriceBoundary(allowed=allow_price)
    trade = ActiveTrade(
        symbol="JPM", trader_type="MOMENTUM", strategy_name="RossMomentumStrategyV1",
        entry_tick=3, entry_price=10.53, direction="LONG", quantity=1,
        stop_loss_price=10.2897, invalidation_level=10.30, take_profit_price=None,
    )
    if open_trade:
        registry.register_trade(trade)
    owner = TradeExitEngine(trade_registry=registry, event_collector=events, price_feed=feed)
    return owner, registry, events, feed, trade


@pytest.mark.parametrize("context", [
    None,
    ShutdownExecutionContext(),
    ShutdownExecutionContext(run_mode="SIM", simulator_backed=True, retained_native_ownership=False),
    ShutdownExecutionContext(run_mode=ShutdownRunMode.SIM, simulator_backed=True),
], ids=["no-context", "unknown-context", "raw-mode-is-not-authority", "unknown-ownership"])
def test_shutdown_unknown_authority_preserves_owned_trade_without_price(context):
    owner, registry, events, feed, trade = _shutdown_owner()
    before = deepcopy(asdict(trade))
    if context is None:
        assert owner.shutdown() is False
        assert registry.snapshot() == [trade] and asdict(trade) == before
    for tick in (7, 70, 700):
        assert owner.shutdown(current_tick=tick, execution_context=context) is False
        assert registry.snapshot() == [trade]
        assert asdict(trade) == before
    assert feed.calls == []
    assert events.snapshot_all() == []


@pytest.mark.parametrize("mode", [ShutdownRunMode.PAPER, ShutdownRunMode.LIVE, ShutdownRunMode.READ_ONLY])
@pytest.mark.parametrize("claimed_simulator", [False, True])
def test_shutdown_native_or_observation_mode_cannot_synthesize_a_protective_exit(mode, claimed_simulator):
    owner, registry, events, feed, trade = _shutdown_owner()
    before = deepcopy(asdict(trade))
    context = ShutdownExecutionContext(
        run_mode=mode,
        simulator_backed=claimed_simulator,
        retained_native_ownership=bool(mode == ShutdownRunMode.PAPER and claimed_simulator),
    )
    # A large explicit tick must not convert protection/resource shutdown into
    # an elapsed-time exit or a locally fabricated fill.
    for tick in (7, 100_000):
        assert owner.shutdown(current_tick=tick, execution_context=context) is False
        assert registry.get_trade("JPM", "MOMENTUM") is trade
        assert asdict(trade) == before
    assert trade.stop_loss_price == 10.2897 and trade.invalidation_level == 10.30
    assert trade.take_profit_price is None and trade.quantity == 1 and trade.state.value == "OPEN"
    assert feed.calls == [] and events.snapshot_all() == []


@pytest.mark.parametrize("mode", [ShutdownRunMode.SIM, ShutdownRunMode.PAPER])
@pytest.mark.parametrize("retained", [True, None, 0, "false"])
def test_shutdown_retained_or_unknown_evidence_overrides_simulator_claim(mode, retained):
    owner, registry, events, feed, trade = _shutdown_owner()
    before = deepcopy(asdict(trade))
    context = ShutdownExecutionContext(
        run_mode=mode, simulator_backed=True, retained_native_ownership=retained,
    )
    assert owner.shutdown(current_tick=100_000, execution_context=context) is False
    assert registry.snapshot() == [trade] and asdict(trade) == before
    assert feed.calls == [] and events.snapshot_all() == []


@pytest.mark.parametrize("mode", [ShutdownRunMode.SIM, ShutdownRunMode.PAPER])
def test_shutdown_explicit_simulator_closes_through_actual_events_and_lifecycle_once(mode):
    owner, registry, events, feed, trade = _shutdown_owner(allow_price=True)
    context = ShutdownExecutionContext(
        run_mode=mode, simulator_backed=True, retained_native_ownership=False,
    )
    assert owner.shutdown(current_tick=7, execution_context=context) is True
    assert registry.snapshot() == [] and trade.state.value == "CLOSED"
    assert feed.calls == [("JPM", 7)]
    closed = events.filter_by_type("TRADE_CLOSED")
    assert len(closed) == 1
    payload = closed[0].payload
    assert payload["mode"] == mode.value and payload["quantity"] == 1
    assert payload["entry_price"] == 10.53 and payload["exit_tick"] == 7
    assert payload["stop_loss_price"] == 10.2897 and payload["take_profit_price"] is None
    assert payload["exit_reason"] == "Forced shutdown exit"
    transitions = events.filter_by_type("LIFECYCLE_TRANSITION")
    assert [row.payload["to_state"] for row in transitions] == ["EXIT_PENDING", "CLOSED"]
    assert all(row.payload["mode"] == mode.value for row in transitions)
    assert all(row.payload["filled_quantity"] == 1 and row.payload["quantity_after"] == 0
        for row in transitions)
    assert len(events.filter_by_type("EXIT_TIME")) == 1
    before = deepcopy(events.snapshot_all())
    assert owner.shutdown(current_tick=8, execution_context=context) is True
    assert feed.calls == [("JPM", 7)] and events.snapshot_all() == before


@pytest.mark.parametrize("mode", [ShutdownRunMode.PAPER, ShutdownRunMode.LIVE, ShutdownRunMode.READ_ONLY])
def test_shutdown_empty_known_native_or_observation_scope_needs_no_synthetic_close(mode):
    owner, registry, events, feed, _ = _shutdown_owner(open_trade=False)
    context = ShutdownExecutionContext(
        run_mode=mode, simulator_backed=False, retained_native_ownership=False,
    )
    assert owner.shutdown(current_tick=7, execution_context=context) is True
    assert owner.shutdown(current_tick=8, execution_context=context) is True
    assert registry.snapshot() == [] and feed.calls == [] and events.snapshot_all() == []


def test_shutdown_empty_registry_cannot_erase_pending_native_ownership():
    owner, registry, events, feed, _ = _shutdown_owner(open_trade=False)
    context = ShutdownExecutionContext(
        run_mode=ShutdownRunMode.PAPER, simulator_backed=False, retained_native_ownership=True,
    )
    assert owner.shutdown(current_tick=7, execution_context=context) is False
    assert owner.shutdown(current_tick=8, execution_context=context) is False
    assert registry.snapshot() == [] and feed.calls == [] and events.snapshot_all() == []
