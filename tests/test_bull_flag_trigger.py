from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_bull_flag import evaluate_bull_flag_trigger
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_bull_flag_trigger_armed_fired_and_filters() -> None:
    payload = {"trigger_level": 10.75, "stop_level": 10.63, "invalidation_level": 10.63}
    armed = evaluate_bull_flag_trigger(
        payload,
        {"candles": _candles([(10.60, 10.72, 10.58, 10.74, 900), (10.74, 10.75, 10.68, 10.73, 910)]), "rvol": 1.3},
    )
    assert armed["trigger_state"] == "ARMED"

    fired = evaluate_bull_flag_trigger(
        payload,
        {"candles": _candles([(10.60, 10.72, 10.58, 10.74, 900), (10.74, 10.86, 10.72, 10.83, 1300)]), "rvol": 1.3, "spread": 0.02},
    )
    assert fired["trigger_state"] == "FIRED"

    blocked_wick = evaluate_bull_flag_trigger(
        payload,
        {"candles": _candles([(10.60, 10.72, 10.58, 10.74, 900), (10.74, 11.00, 10.72, 10.78, 1800)]), "rvol": 1.4},
    )
    assert blocked_wick["trigger_state"] == "BLOCKED"

    blocked_liquidity = evaluate_bull_flag_trigger(
        payload,
        {"candles": _candles([(10.60, 10.72, 10.58, 10.74, 1800), (10.74, 10.86, 10.72, 10.83, 700)]), "rvol": 0.8},
    )
    assert blocked_liquidity["trigger_state"] == "BLOCKED"

    blocked_spread = evaluate_bull_flag_trigger(
        payload,
        {"candles": _candles([(10.60, 10.72, 10.58, 10.74, 900), (10.74, 10.86, 10.72, 10.83, 1300)]), "rvol": 1.3, "spread": 0.09},
    )
    assert blocked_spread["trigger_state"] == "BLOCKED"


def test_bull_flag_trigger_registry_mapping() -> None:
    assert resolve_trigger_evaluator("BULL_FLAG") is not None
