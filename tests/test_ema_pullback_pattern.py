from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_ema_pullback import detect_ema_pullback
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles: list[Candle], *, ema9: float = 10.44, ema20: float = 10.30, rvol: float = 1.8) -> PatternInputs:
    return PatternInputs(
        symbol="EMA",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.8, premarket_low=9.9, hod=10.9, prior_close=10.0),
        indicators=IndicatorSet(ema9=ema9, ema20=ema20, vwap=10.36),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=rvol),
        news_context={"macd": 0.4},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(10.00, 10.10, 9.98, 10.08, 900),
        Candle(10.08, 10.30, 10.06, 10.25, 1250),
        Candle(10.25, 10.52, 10.22, 10.48, 1600),
        Candle(10.48, 10.50, 10.31, 10.33, 920),
        Candle(10.33, 10.39, 10.29, 10.35, 860),
        Candle(10.35, 10.62, 10.34, 10.56, 1500),
    ]


def test_detects_valid_ema_pullback() -> None:
    result = detect_ema_pullback(_inputs(_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_EMA_PULLBACK"
    assert result.setup_family_id == "EMA_PULLBACK"
    assert result.signal_class == "ENTRY"
    assert result.trigger_mode == "RECLAIM_BREAKOUT"


def test_rejects_missing_ema_test() -> None:
    candles = _valid_candles()
    candles[-2] = Candle(10.48, 10.50, 10.46, 10.47, 920)
    candles[-1] = Candle(10.47, 10.62, 10.45, 10.56, 1500)
    result = detect_ema_pullback(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "no_ema_test"


def test_rejects_no_reclaim() -> None:
    candles = _valid_candles()
    candles[-2] = Candle(10.48, 10.50, 10.31, 10.46, 920)
    candles[-1] = Candle(10.46, 10.62, 10.34, 10.56, 1500)
    result = detect_ema_pullback(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "no_ema_reclaim"


def test_rejects_weak_trend() -> None:
    result = detect_ema_pullback(_inputs(_valid_candles(), ema9=10.28, ema20=10.36))
    assert result.detected is False
    assert result.rejection_reason == "no_trend_alignment"
