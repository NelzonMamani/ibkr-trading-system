from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_hod_break import detect_hod_break
from src.strategies.common.triggers.trigger_hod_break import evaluate_hod_break_trigger
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs(*, session: SessionContext = SessionContext.REGULAR, hod: float | None = 10.52, candles: list[Candle] | None = None) -> PatternInputs:
    return PatternInputs(
        symbol="HODT",
        timeframe="1MIN",
        candles=candles
        or _candles(
            [
                (10.20, 10.28, 10.18, 10.26, 1000),
                (10.26, 10.36, 10.24, 10.34, 1100),
                (10.34, 10.44, 10.34, 10.40, 1200),
                (10.40, 10.50, 10.39, 10.46, 1300),
                (10.46, 10.51, 10.44, 10.50, 1250),
                (10.49, 10.52, 10.47, 10.51, 1400),
            ]
        ),
        session_context=session,
        levels=LevelSet(premarket_high=10.1, premarket_low=9.7, hod=hod, prior_close=9.9, key_levels={}),
        indicators=IndicatorSet(ema9=10.45, ema20=10.36, vwap=10.41),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=18.0, rvol=1.9),
    )


def test_hod_break_detects_valid_compression_and_breakout_ready() -> None:
    result = detect_hod_break(_inputs())
    assert result.detected is True
    assert result.setup_id == "P_HOD_BREAK"
    assert result.setup_family_id == "HOD_BREAK"
    assert result.trigger_type == "XL_HOD_BREAK"


def test_hod_break_rejects_invalid_session() -> None:
    result = detect_hod_break(_inputs(session=SessionContext.PRE))
    assert result.detected is False
    assert result.rejection_reason == "invalid_session"


def test_hod_break_rejects_when_hod_missing() -> None:
    malformed = [
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
        {"open": 10.0, "high": None, "low": 9.9, "close": 10.0, "volume": 1000},
    ]
    result = detect_hod_break(_inputs(hod=None, candles=malformed))
    assert result.detected is False
    assert result.rejection_reason == "missing_hod"


def test_hod_break_rejects_without_compression() -> None:
    wide = _candles(
        [
            (10.2, 10.35, 10.1, 10.3, 1000),
            (10.3, 10.46, 10.2, 10.35, 1200),
            (10.35, 10.51, 10.2, 10.4, 1200),
            (10.4, 10.52, 10.21, 10.48, 1300),
            (10.48, 10.54, 10.22, 10.5, 1300),
            (10.5, 10.55, 10.24, 10.51, 1400),
        ]
    )
    result = detect_hod_break(_inputs(candles=wide, hod=10.55))
    assert result.detected is False
    assert result.rejection_reason == "no_compression"


def test_hod_break_trigger_arms_and_fires() -> None:
    armed = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.50, 1000), (10.50, 10.52, 10.49, 10.51, 1100)])},
    )
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluate_hod_break_trigger(
        {"trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.56, 10.50, 10.54, 1500)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_trigger_registry_contains_hod_break() -> None:
    assert "HOD_BREAK" in TRIGGER_EVALUATOR_REGISTRY
    assert resolve_trigger_evaluator("HOD_BREAK") is not None


def test_ross_runtime_can_consume_hod_break_without_bypass() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [pattern for pattern in registry.patterns if getattr(pattern, "pattern_id", "") == "P_HOD_BREAK"]

    result = registry.run(_inputs())[0]
    assert result.setup_id == "P_HOD_BREAK"
    assert result.setup_family_id == "HOD_BREAK"
    assert result.trigger_type == "XL_HOD_BREAK"

    evaluator = resolve_trigger_evaluator(result.setup_family_id)
    assert evaluator is not None
    trigger = evaluator(
        {"trigger_level": result.trigger_level, "invalidation_level": result.invalidation_level, "stop_level": result.stop_level},
        {"candles": _inputs().candles},
    )
    assert trigger["trigger_type"] == "XL_HOD_BREAK"
