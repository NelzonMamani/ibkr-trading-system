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
