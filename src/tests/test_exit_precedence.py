from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.runtime_config import RuntimeConfig  # noqa: E402
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from core.event_collector import EventCollector  # noqa: E402
from execution.trade_exit_engine import ExitDecision, TradeExitEngine  # noqa: E402
from sim.price_feed import DeterministicPriceFeed  # noqa: E402


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
    )
    defaults.update(overrides)
    return ActiveTrade(**defaults)


def test_exit_precedence_matrix_honours_highest_priority_condition():
    engine = _build_engine()
    config = RuntimeConfig(min_hold_ticks=2, max_hold_ticks=5)

    scenarios = [
        {
            "name": "Max hold overrides price exits and strategy signals",
            "trade": _build_trade(
                stop_loss_price=110.0,
                take_profit_price=90.0,
            ),
            "tick": 5,
            "current_price": 90.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                should_exit=True,
                reason="TIME_MAX",
                rationale="Exit condition met: maximum hold duration reached via TradeExitEngine (held 5 ticks; max_hold_ticks=5)",
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
                should_exit=True,
                reason="PRICE_STOP",
                rationale="Exit condition met: stop-loss price reached via TradeExitEngine (direction=LONG price=105.0 stop_loss_price=105.0)",
            ),
        },
        {
            "name": "Take-profit fires even before minimum hold threshold",
            "trade": _build_trade(
                take_profit_price=101.0,
                stop_loss_price=None,
            ),
            "tick": 1,
            "current_price": 101.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                should_exit=True,
                reason="PRICE_TP",
                rationale="Exit condition met: take-profit price reached via TradeExitEngine (direction=LONG price=101.0 take_profit_price=101.0)",
            ),
        },
        {
            "name": "Minimum hold blocks strategy exit when no price overrides",
            "trade": _build_trade(),
            "tick": 1,
            "current_price": 100.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                should_exit=False,
                reason="TIME_MIN_BLOCK",
                rationale="Minimum hold duration not yet reached — strategy exits blocked (held 1 ticks; min_hold_ticks=2)",
            ),
        },
        {
            "name": "Strategy exit allowed after minimum hold with no other triggers",
            "trade": _build_trade(),
            "tick": 3,
            "current_price": 100.0,
            "strategy_exit_signal": True,
            "expected": ExitDecision(
                should_exit=True,
                reason="STRATEGY_SIGNAL",
                rationale="Strategy exit request honoured by TradeExitEngine",
            ),
        },
        {
            "name": "Hold when no exit criteria are met",
            "trade": _build_trade(),
            "tick": 3,
            "current_price": 100.0,
            "strategy_exit_signal": False,
            "expected": ExitDecision(
                should_exit=False,
                reason="HOLD",
                rationale="No exit condition met — holding trade open.",
            ),
        },
    ]

    for scenario in scenarios:
        decision = engine.decide_exit(
            trade=scenario["trade"],
            tick=scenario["tick"],
            current_price=scenario["current_price"],
            strategy_exit_signal=scenario["strategy_exit_signal"],
            config=config,
        )
        assert decision.should_exit == scenario["expected"].should_exit, scenario["name"]
        assert decision.reason == scenario["expected"].reason, scenario["name"]
        assert decision.rationale == scenario["expected"].rationale, scenario["name"]


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
        tick=3,
        current_price=95.5,
        strategy_exit_signal=False,
        config=config,
    )

    assert decision.reason == "PRICE_STOP"
    assert decision.should_exit

    tp_decision = engine.decide_exit(
        trade=trade,
        tick=2,
        current_price=89.0,
        strategy_exit_signal=False,
        config=config,
    )

    assert tp_decision.reason == "PRICE_TP"
    assert tp_decision.should_exit
