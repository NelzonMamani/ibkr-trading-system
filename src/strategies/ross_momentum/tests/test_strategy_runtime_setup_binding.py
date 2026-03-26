from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.strategy_contracts import Direction, MarketContext, ScannerContext, SessionContext, StrategyInput


def _candles(rows: list[tuple[float, float, float, float, int]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_runtime_path_emits_intent_for_entry_family() -> None:
    strategy = RossMomentumStrategy()
    candles = _candles(
        [
            (10.0, 10.2, 9.95, 10.15, 900),
            (10.15, 10.35, 10.1, 10.3, 1000),
            (10.3, 10.32, 10.2, 10.24, 800),
            (10.24, 10.25, 10.16, 10.18, 780),
            (10.18, 10.2, 10.1, 10.12, 760),
            (10.15, 10.42, 10.14, 10.4, 1200),
        ]
    )
    pattern_inputs = [
        PatternInputs(
            symbol="TEST",
            timeframe="1m",
            candles=candles,
            session_context=SessionContext.REGULAR,
            levels=LevelSet(premarket_high=10.25, premarket_low=9.9, hod=10.35, prior_close=9.8),
            indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18),
            liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.5),
        )
    ]
    decision = strategy.evaluate(
        "TEST",
        StrategyInput(
            symbol="TEST",
            session_context=SessionContext.REGULAR,
            scanner_context=ScannerContext(score=0.9, rank=1),
            market_context=MarketContext(
                price=10.45,
                spread=0.02,
                volume=150_000,
                rvol=2.5,
                session_label="RTH_OPEN",
                key_levels={"HOD": 10.35, "PREMARKET_HIGH": 10.25},
            ),
            pattern_inputs=pattern_inputs,
            news_context={"session_phase": "RTH_OPEN"},
        ),
    )
    assert decision.intents, "Expected at least one intent from concrete setup-trigger path"
    assert decision.intents[0].direction == Direction.LONG


def test_runtime_path_blocks_non_entry_family() -> None:
    strategy = RossMomentumStrategy()
    candles = _candles(
        [
            (10, 10.2, 9.98, 10.18, 900),
            (10.18, 10.45, 10.16, 10.4, 1000),
            (10.4, 10.78, 10.38, 10.7, 1200),
            (10.7, 11.2, 10.68, 11.05, 1500),
            (11.05, 11.8, 11.0, 11.65, 1900),
            (11.65, 12.4, 11.5, 11.75, 3200),
        ]
    )
    pattern_inputs = [
        PatternInputs(
            symbol="WARN",
            timeframe="1m",
            candles=candles,
            session_context=SessionContext.REGULAR,
            levels=LevelSet(premarket_high=12.5, premarket_low=9.9, hod=12.0, prior_close=9.8),
            indicators=IndicatorSet(ema9=12.0, ema20=12.0, vwap=12.0),
            liquidity_context=LiquidityContext(spread=0.03, float_millions=20.0, rvol=3.2),
        )
    ]
    decision = strategy.evaluate(
        "WARN",
        StrategyInput(
            symbol="WARN",
            session_context=SessionContext.REGULAR,
            scanner_context=ScannerContext(score=0.8, rank=2),
            market_context=MarketContext(
                price=11.7,
                spread=0.03,
                    volume=200_000,
                    rvol=3.2,
                    session_label="RTH_OPEN",
                    key_levels={"HOD": 12.0, "PREMARKET_HIGH": 12.5},
                ),
            pattern_inputs=pattern_inputs,
            news_context={"session_phase": "RTH_OPEN"},
        ),
    )
    assert not decision.intents
