from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config.runtime_config import RuntimeConfig  # noqa: E402
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from src.core.event_collector import EventCollector  # noqa: E402
from src.execution.trade_exit_engine import ExitDecision, TradeExitEngine  # noqa: E402
from src.sim.price_feed import DeterministicPriceFeed  # noqa: E402


def _build_engine() -> TradeExitEngine:
    return TradeExitEngine(
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
    )


def _build_trade(**overrides) -> ActiveTrade:
    defaults = dict(
        symbol="TEST",
        trader_type="SIM_TRADER",
        entry_tick=0,
        entry_price=100.0,
        direction="LONG",
        quantity=1,
        strategy_name="StrategyX",
        stop_loss_price=99.0,
    )
    defaults.update(overrides)
    return ActiveTrade(**defaults)


def test_exit_precedence_matrix_honours_highest_priority_condition():
    engine = _build_engine()
    config = RuntimeConfig(min_hold_ticks=2, max_hold_ticks=5)

    scenarios = [
        {
            "name": "Stop-loss overrides time-based exits and strategy signals",
            "trade": _build_trade(
                stop_loss_price=110.0,
                take_profit_price=90.0,
            ),
            "tick": 5,
            "current_price": 90.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                category="EXIT_FAILED_SETUP",
                reason="Pattern invalidation / failed breakout — stop-loss breached",
                exit_tick=5,
                exit_price=90.0,
            ),
        },
        {
            "name": "Stop-loss overrides take-profit when both thresholds are satisfied",
            "trade": _build_trade(
                stop_loss_price=105.0,
                take_profit_price=100.0,
            ),
            "tick": 4,
            "current_price": 105.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                category="EXIT_FAILED_SETUP",
                reason="Pattern invalidation / failed breakout — stop-loss breached",
                exit_tick=4,
                exit_price=105.0,
            ),
        },
        {
            "name": "Take-profit fires even before minimum hold threshold",
            "trade": _build_trade(
                take_profit_price=101.0,
                stop_loss_price=99.0,
            ),
            "tick": 1,
            "current_price": 101.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                category="EXIT_TARGET",
                reason="Profit target reached",
                exit_tick=1,
                exit_price=101.0,
            ),
        },
        {
            "name": "Minimum hold blocks strategy exit when no price overrides",
            "trade": _build_trade(),
            "tick": 1,
            "current_price": 100.5,
            "strategy_exit_signal": True,
            "expected": None,
        },
        {
            "name": "Strategy exit allowed after minimum hold with no other triggers",
            "trade": _build_trade(),
            "tick": 3,
            "current_price": 100.7,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                category="EXIT_STRATEGY",
                reason="Strategy requested exit",
                exit_tick=3,
                exit_price=100.7,
            ),
        },
        {
            "name": "Hold when no exit criteria are met",
            "trade": _build_trade(),
            "tick": 2,
            "current_price": 100.5,
            "strategy_exit_signal": False,
            "expected": None,
        },
    ]

    for scenario in scenarios:
        decision = engine.decide_exit(
            trade=scenario["trade"],
            current_tick=scenario["tick"],
            current_price=scenario["current_price"],
            strategy_exit_signal=scenario["strategy_exit_signal"],
            config=config,
        )
        expected = scenario["expected"]
        if expected is None:
            assert decision is None, scenario["name"]
        else:
            assert decision is not None, scenario["name"]
            assert decision.category == expected.category, scenario["name"]
            assert decision.reason == expected.reason, scenario["name"]
            assert decision.exit_tick == expected.exit_tick, scenario["name"]
            assert decision.exit_price == expected.exit_price, scenario["name"]


def test_price_exit_precedence_for_short_trades():
    engine = _build_engine()
    config = RuntimeConfig(min_hold_ticks=1, max_hold_ticks=10)

    trade = _build_trade(
        direction="SHORT",
        stop_loss_price=95.0,
        take_profit_price=90.0,
    )

    decision = engine.decide_exit(
        trade=trade,
        current_tick=3,
        current_price=95.5,
        strategy_exit_signal=False,
        config=config,
    )

    assert decision is not None
    assert decision.category == "EXIT_FAILED_SETUP"

    tp_decision = engine.decide_exit(
        trade=trade,
        current_tick=2,
        current_price=89.0,
        strategy_exit_signal=False,
        config=config,
    )

    assert tp_decision is not None
    assert tp_decision.category == "EXIT_TARGET"
