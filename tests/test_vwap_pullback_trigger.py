from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.common.triggers.trigger_vwap_pullback import evaluate_vwap_pullback_trigger


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_vwap_pullback_trigger_armed_to_fired_transition() -> None:
    payload = {"trigger_level": 10.55, "stop_level": 10.29, "invalidation_level": 10.29}
    armed = evaluate_vwap_pullback_trigger(
        payload,
        {"candles": _candles([(10.33, 10.52, 10.30, 10.54, 1100), (10.54, 10.55, 10.50, 10.54, 1000)]), "rvol": 1.4},
    )
    assert armed["trigger_state"] == "ARMED"

    fired = evaluate_vwap_pullback_trigger(
        payload,
        {"candles": _candles([(10.33, 10.52, 10.30, 10.54, 1100), (10.54, 10.66, 10.52, 10.62, 1800)]), "rvol": 1.5},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_reason"] == "vwap_pullback_breakout_confirmed"


def test_vwap_pullback_trigger_rejects_wick_only_breakout() -> None:
    payload = {"trigger_level": 10.55, "stop_level": 10.29, "invalidation_level": 10.29}
    blocked = evaluate_vwap_pullback_trigger(
        payload,
        {"candles": _candles([(10.33, 10.52, 10.30, 10.54, 1200), (10.54, 10.78, 10.52, 10.57, 2200)]), "rvol": 1.6},
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "breakout_shape_invalid"


def test_vwap_pullback_trigger_rejects_low_volume_breakout() -> None:
    payload = {"trigger_level": 10.55, "stop_level": 10.29, "invalidation_level": 10.29}
    blocked = evaluate_vwap_pullback_trigger(
        payload,
        {
            "candles": _candles([(10.33, 10.52, 10.30, 10.54, 1800), (10.54, 10.66, 10.52, 10.62, 700)]),
            "rvol": 1.0,
            "avg_volume": 1400,
        },
    )
    assert blocked["trigger_state"] == "BLOCKED"
    assert blocked["trigger_reason"] == "liquidity_confirmation_failed"


def test_trigger_registry_contains_vwap_pullback() -> None:
    assert resolve_trigger_evaluator("VWAP_PULLBACK") is not None
