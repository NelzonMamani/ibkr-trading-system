"""Ross trade-ready smoke using crafted candles to force at least one detection and intent."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.strategy_contracts import MarketContext, ScannerContext, SessionContext, StrategyInput


def _crafted_gap_go_inputs() -> PatternInputs:
    candles = [
        Candle(open=10.9, high=11.0, low=10.85, close=10.95, volume=120_000),
        Candle(open=11.05, high=11.22, low=11.0, close=11.2, volume=190_000),
        Candle(open=11.21, high=11.4, low=11.18, close=11.37, volume=260_000),
        Candle(open=11.35, high=11.55, low=11.32, close=11.52, volume=300_000),
    ]
    return PatternInputs(
        symbol="SMOKE",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=11.2, prior_close=10.8, hod=11.5, key_levels={"whole": 11.0}),
        indicators=IndicatorSet(ema9=11.25, ema20=11.1, vwap=11.24),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=20.0, rvol=2.1),
    )


def main() -> int:
    strategy = RossMomentumStrategy()
    pattern_input = _crafted_gap_go_inputs()
    decision = strategy.evaluate(
        symbol="SMOKE",
        inputs=StrategyInput(
            symbol="SMOKE",
            session_context=SessionContext.REGULAR,
            scanner_context=ScannerContext(score=90.0, rank=1),
            market_context=MarketContext(price=11.52, spread=0.02, volume=300_000, rvol=2.1),
            pattern_inputs=[pattern_input],
        ),
    )

    detected = [r for r in strategy._evaluator.evaluate([pattern_input]).all_results if r.detected]
    assert detected, "Expected at least one detected setup from crafted candles"
    assert decision.intents, "Expected at least one emitted intent"
    print("PASS: ross_trade_ready_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
