from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.common.triggers.trigger_stair_step import evaluate_stair_step_trigger


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_stair_step_trigger_armed_to_fired_transition() -> None:
    payload = {"trigger_level": 10.60, "stop_level": 10.34, "invalidation_level": 10.24}
    armed = evaluate_stair_step_trigger(
        payload,
        {"candles": _candles([(10.42, 10.55, 10.38, 10.56, 1000), (10.56, 10.60, 10.50, 10.59, 1200)]), "rvol": 1.5},
    )
    assert armed["trigger_state"] == "ARMED"

    fired = evaluate_stair_step_trigger(
        payload,
        {"candles": _candles([(10.42, 10.55, 10.38, 10.59, 1000), (10.59, 10.68, 10.56, 10.65, 1600)]), "rvol": 1.5},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_reason"] == "stair_step_breakout_confirmed"


def test_stair_step_trigger_rejects_wick_only_breakout() -> None:
    payload = {"trigger_level": 10.60, "stop_level": 10.34, "invalidation_level": 10.24}
    blocked = evaluate_stair_step_trigger(
        payload,
        {"candles": _candles([(10.42, 10.55, 10.38, 10.59, 1000), (10.59, 10.82, 10.56, 10.62, 1800)]), "rvol": 1.5},
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "breakout_shape_invalid"


def test_stair_step_trigger_rejects_low_volume_breakout() -> None:
    payload = {"trigger_level": 10.60, "stop_level": 10.34, "invalidation_level": 10.24}
    blocked = evaluate_stair_step_trigger(
        payload,
        {
            "candles": _candles([(10.42, 10.55, 10.38, 10.59, 1500), (10.59, 10.68, 10.56, 10.65, 700)]),
            "rvol": 1.0,
            "avg_volume": 1200,
        },
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "liquidity_confirmation_failed"


def test_trigger_registry_contains_stair_step_family() -> None:
    assert resolve_trigger_evaluator("TREND_CONTINUATION_STAIR_STEP") is not None
