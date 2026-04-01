from __future__ import annotations

from types import SimpleNamespace

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_opening_drive import detect_opening_drive
from src.strategies.common.triggers.trigger_opening_drive import evaluate_opening_drive_trigger
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(*, session: SessionContext = SessionContext.REGULAR, candles: list[Candle] | None = None) -> PatternInputs:
    return PatternInputs(
        symbol="TEST",
        timeframe="1MIN",
        candles=candles
        or [
            Candle(10.0, 10.18, 9.99, 10.16, 1600),
            Candle(10.16, 10.32, 10.15, 10.30, 1750),
            Candle(10.30, 10.46, 10.28, 10.42, 1900),
            Candle(10.42, 10.52, 10.40, 10.50, 1650),
            Candle(10.50, 10.60, 10.47, 10.58, 1800),
        ],
        session_context=session,
        levels=LevelSet(premarket_high=10.2, premarket_low=9.8, hod=10.6, lod=9.8, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.35, ema20=10.2, vwap=10.3),
        liquidity_context=LiquidityContext(spread=0.01, rvol=2.3, float_millions=15.0),
    )


def test_opening_drive_pattern_detects_valid_open_impulse() -> None:
    result = detect_opening_drive(_inputs())
    assert result.detected is True
    assert result.setup_id == "P_OPENING_DRIVE"
    assert result.setup_family_id == "OPENING_DRIVE"
    assert result.trigger_type == "XL_OPENING_DRIVE_BREAK"


def test_opening_drive_pattern_rejects_invalid_session() -> None:
    result = detect_opening_drive(_inputs(session=SessionContext.PRE))
    assert result.detected is False
    assert result.rejection_reason == "invalid_session"


def test_opening_drive_rejects_non_rth_open_if_phase_available() -> None:
    base = _inputs()
    payload = {**base.__dict__, "session_phase": "RTH_MID"}
    result = detect_opening_drive(SimpleNamespace(**payload))
    assert result.detected is False
    assert result.rejection_reason == "invalid_phase"


def test_opening_drive_trigger_arms_and_fires() -> None:
    armed = evaluate_opening_drive_trigger(
        {"trigger_level": 10.62, "invalidation_level": 10.45},
        {"candles": [{"high": 10.60, "close": 10.59}]},
    )
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluate_opening_drive_trigger(
        {"trigger_level": 10.62, "invalidation_level": 10.45},
        {"candles": [{"high": 10.64, "close": 10.63}]},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_trigger_registry_contains_opening_drive() -> None:
    evaluator = resolve_trigger_evaluator("OPENING_DRIVE")
    assert evaluator is not None
