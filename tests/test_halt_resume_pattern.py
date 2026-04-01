from __future__ import annotations

from datetime import datetime, timedelta

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_halt_resume import detect_halt_resume
from src.strategies.common.patterns.pattern_registry import PATTERN_DETECTORS
from src.strategies.common.triggers.trigger_halt_resume import evaluate_halt_resume_trigger
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles: list[Candle], *, spread: float = 0.02, rvol: float = 1.6) -> PatternInputs:
    return PatternInputs(
        symbol="HALT",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=11.0, premarket_low=10.0, hod=11.2, lod=9.9, prior_close=10.5),
        indicators=IndicatorSet(ema9=10.9, ema20=10.8, vwap=10.85),
        liquidity_context=LiquidityContext(spread=spread, rvol=rvol, float_millions=15.0),
    )


def _valid_halt_resume_candles() -> list[Candle]:
    t0 = datetime(2026, 1, 2, 14, 30, 0)
    return [
        Candle(10.00, 10.08, 9.98, 10.05, 1200, t0),
        Candle(10.05, 10.11, 10.02, 10.08, 1100, t0 + timedelta(minutes=1)),
        Candle(10.08, 10.95, 10.05, 10.86, 5000, t0 + timedelta(minutes=6)),
        Candle(10.86, 10.95, 10.60, 10.78, 2300, t0 + timedelta(minutes=7)),
        Candle(10.78, 10.88, 10.62, 10.76, 1900, t0 + timedelta(minutes=8)),
        Candle(10.76, 10.89, 10.65, 10.80, 2100, t0 + timedelta(minutes=9)),
        Candle(10.80, 10.87, 10.66, 10.81, 2000, t0 + timedelta(minutes=10)),
    ]


def test_halt_resume_detects_valid_halt_and_stabilization() -> None:
    result = detect_halt_resume(_inputs(_valid_halt_resume_candles()))
    assert result.detected is True
    assert result.setup_id == "P_HALT_RESUME"
    assert result.setup_family_id == "HALT_RESUME"
    assert result.trigger_type == "XL_HALT_RESUME_BREAK"


def test_halt_resume_rejects_when_no_halt_gap() -> None:
    candles = _valid_halt_resume_candles()
    no_gap = [candles[0], candles[1]]
    t = candles[1].timestamp
    assert t is not None
    for c in candles[2:]:
        t = t + timedelta(minutes=1)
        no_gap.append(Candle(c.open, c.high, c.low, c.close, c.volume, t))
    result = detect_halt_resume(_inputs(no_gap))
    assert result.detected is False
    assert result.rejection_reason == "no_halt_detected"


def test_halt_resume_rejects_without_stabilization_window() -> None:
    result = detect_halt_resume(_inputs(_valid_halt_resume_candles()[:5]))
    assert result.detected is False
    assert result.rejection_reason == "insufficient_stabilization"


def test_halt_resume_rejects_wide_spread() -> None:
    result = detect_halt_resume(_inputs(_valid_halt_resume_candles(), spread=0.25))
    assert result.detected is False
    assert result.rejection_reason == "wide_spread"


def test_halt_resume_trigger_armed_and_fired() -> None:
    armed = evaluate_halt_resume_trigger(
        {"trigger_level": 10.9, "stop_level": 10.6},
        {"candles": [{"high": 10.89, "close": 10.88}, {"high": 10.90, "close": 10.89}]},
    )
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluate_halt_resume_trigger(
        {"trigger_level": 10.9, "stop_level": 10.6},
        {"candles": [{"high": 10.89, "close": 10.88}, {"high": 10.95, "close": 10.92}]},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_halt_resume_registry_wiring() -> None:
    assert "P_HALT_RESUME" in PATTERN_DETECTORS
    assert "HALT_RESUME" in TRIGGER_EVALUATOR_REGISTRY
    assert resolve_trigger_evaluator("HALT_RESUME") is not None


def test_ross_runtime_can_consume_halt_resume_without_bypass() -> None:
    strategy = RossMomentumStrategyV1()
    filtered = strategy._filter_trusted_pattern_results(
        [
            {
                "setup_family_id": "HALT_RESUME",
                "pattern_id": "P_HALT_RESUME",
                "detected": True,
                "confidence": 0.79,
            }
        ],
        symbol="HALT",
    )
    assert filtered[0].get("untrusted") is not True
