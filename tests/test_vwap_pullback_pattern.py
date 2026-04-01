from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_vwap_pullback import detect_vwap_pullback
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles: list[Candle], *, vwap: float = 10.35, rvol: float = 1.8) -> PatternInputs:
    return PatternInputs(
        symbol="VWAP",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.8, premarket_low=9.9, hod=10.9, prior_close=10.0),
        indicators=IndicatorSet(ema9=10.48, ema20=10.32, vwap=vwap),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=rvol),
        news_context={"macd": 0.4},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(10.00, 10.08, 9.98, 10.06, 900),
        Candle(10.06, 10.24, 10.04, 10.22, 1100),
        Candle(10.22, 10.54, 10.20, 10.50, 1650),
        Candle(10.50, 10.56, 10.30, 10.33, 900),
        Candle(10.33, 10.38, 10.29, 10.34, 850),
        Candle(10.34, 10.58, 10.33, 10.52, 1500),
    ]


def test_detects_valid_vwap_pullback() -> None:
    result = detect_vwap_pullback(_inputs(_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_VWAP_PULLBACK"
    assert result.setup_family_id == "VWAP_PULLBACK"
    assert result.trigger_mode == "RECLAIM_BREAKOUT"


def test_rejects_no_reclaim() -> None:
    candles = _valid_candles()
    candles[-1] = Candle(10.34, 10.42, 10.30, 10.34, 1300)
    result = detect_vwap_pullback(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "no_vwap_reclaim"


def test_rejects_heavy_selling() -> None:
    candles = _valid_candles()
    candles[-2] = Candle(10.50, 10.52, 10.28, 10.33, 2600)
    candles[-1] = Candle(10.33, 10.58, 10.31, 10.52, 1500)
    result = detect_vwap_pullback(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "selling_pressure_too_high"


def test_rejects_weak_trend_context() -> None:
    candles = [
        Candle(10.40, 10.45, 10.30, 10.35, 1000),
        Candle(10.35, 10.40, 10.22, 10.28, 980),
        Candle(10.28, 10.33, 10.16, 10.20, 950),
        Candle(10.20, 10.26, 10.12, 10.15, 940),
        Candle(10.15, 10.22, 10.08, 10.12, 920),
        Candle(10.12, 10.18, 10.05, 10.10, 900),
    ]
    result = detect_vwap_pullback(_inputs(candles, vwap=10.25))
    assert result.detected is False
    assert result.rejection_reason == "no_trend_context"
