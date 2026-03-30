from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_first_pullback_and_premarket_high_break_emit_invoke_and_result_logs(capsys) -> None:
    registry = RossPatternRegistry()
    registry._patterns = [
        pattern
        for pattern in registry.patterns
        if getattr(pattern, "pattern_id", "") in {"P_FIRST_PULLBACK", "P_PREMKT_BREAK"}
    ]

    inputs = PatternInputs(
        symbol="TST",
        timeframe="1m",
        candles=_candles(
            [
                (10.0, 10.3, 9.95, 10.25, 1000),
                (10.25, 10.6, 10.2, 10.55, 1200),
                (10.55, 10.9, 10.5, 10.85, 1500),
                (10.85, 10.86, 10.72, 10.75, 900),
                (10.75, 10.78, 10.68, 10.7, 850),
                (10.72, 10.95, 10.71, 10.92, 1300),
            ]
        ),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.9, hod=10.95, prior_close=9.8),
        indicators=IndicatorSet(ema9=10.7, ema20=10.6, vwap=10.62),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.0),
    )

    results = registry.run(inputs)
    by_id = {result.setup_id: result for result in results}

    assert by_id["P_FIRST_PULLBACK"].detected is True
    assert by_id["P_PREMKT_BREAK"].detected is True

    output = capsys.readouterr().out
    assert "[SETUP][INVOKE] name=FIRST_PULLBACK" in output
    assert "[SETUP][INVOKE] name=PREMARKET_HIGH_BREAK" in output
    assert "[SETUP][RESULT] name=FIRST_PULLBACK detected=True reason=detected" in output
    assert "[SETUP][RESULT] name=PREMARKET_HIGH_BREAK detected=True reason=detected" in output
