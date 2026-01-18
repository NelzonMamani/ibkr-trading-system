from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import (
    MarketContext,
    ScannerContext,
    SessionContext,
    StrategyInput,
)
from src.strategies.strategy_registry import build_default_registry


def _sample_pattern_inputs(symbol: str) -> PatternInputs:
    candles = [
        Candle(open=10.0, high=10.3, low=9.9, close=10.25, volume=1200),
        Candle(open=10.25, high=10.5, low=10.1, close=10.4, volume=1500),
        Candle(open=10.4, high=10.65, low=10.3, close=10.6, volume=1800),
        Candle(open=10.6, high=10.8, low=10.5, close=10.75, volume=1700),
        Candle(open=10.75, high=10.95, low=10.7, close=10.9, volume=2000),
        Candle(open=10.9, high=11.1, low=10.85, close=11.0, volume=2200),
    ]
    indicators = IndicatorSet(ema9=10.6, ema20=10.4, vwap=10.5)
    levels = LevelSet(premarket_high=10.9, hod=11.2, prior_close=9.8)
    liquidity = LiquidityContext(spread=0.02, float_millions=18.0, rvol=2.2)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
    )


def test_registry_loads_ross_strategy_and_evaluates() -> None:
    registry = build_default_registry(enabled_strategy_ids=["ross_momentum"])
    inputs = StrategyInput(
        symbol="TEST",
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=0.8, rank=1),
        market_context=MarketContext(price=11.0, spread=0.02, volume=200000, rvol=2.5),
        pattern_inputs=[_sample_pattern_inputs("TEST")],
    )
    decisions = registry.evaluate_symbol("TEST", inputs)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.strategy_id == "ross_momentum"
    assert decision.symbol == "TEST"
