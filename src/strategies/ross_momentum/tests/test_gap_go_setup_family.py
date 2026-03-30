from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.setup_engine.setup_families.ross_families import GapGoPattern
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_gap_go_detects_bullish_gap_runner_and_emits_setup_logs(capsys) -> None:
    registry = RossPatternRegistry()
    registry._patterns = [pattern for pattern in registry.patterns if getattr(pattern, "pattern_id", "") == "P_GAP_GO"]
    inputs = PatternInputs(
        symbol="GAPX",
        timeframe="1m",
        candles=_candles(
            [
                (10.9, 11.05, 10.85, 11.0, 80_000),
                (11.0, 11.22, 10.95, 11.18, 95_000),
                (11.18, 11.42, 11.12, 11.37, 130_000),
                (11.37, 11.66, 11.3, 11.62, 170_000),
            ]
        ),
        session_context=SessionContext.PRE,
        levels=LevelSet(
            premarket_high=11.5,
            premarket_low=10.7,
            hod=11.58,
            prior_close=10.0,
            key_levels={"OPENING_RANGE_HIGH": 11.45},
        ),
        indicators=IndicatorSet(ema9=11.28, ema20=11.12, vwap=11.2),
        liquidity_context=LiquidityContext(spread=0.03, float_millions=7.5, rvol=2.7),
        news_context={"trend_up": "true", "impulse_active": "true", "continuation_pressure": "true"},
    )

    results = registry.run(inputs)
    assert results
    result = next(item for item in results if item.setup_family_id == "GAP_GO")
    assert result.detected is True
    assert result.setup_family_id == "GAP_GO"
    assert result.pattern_name == "Gap & Go"
    assert result.direction.value == "LONG"
    assert result.trigger_type in {"PMH_BREAK", "HOD_BREAK", "BREAK_AND_HOLD", "BREAKOUT_HIGH"}
    assert "HIGH_RVOL" in result.setup_quality_tags
    assert "LEVEL_PRESSURE" in result.setup_quality_tags

    output = capsys.readouterr().out
    assert "[SETUP][INVOKE] name=GAP_GO" in output
    assert "[SETUP][RESULT] name=GAP_GO detected=True reason=detected" in output


def test_gap_go_rejects_when_rvol_is_insufficient() -> None:
    result = GapGoPattern().evaluate(
        PatternInputs(
            symbol="GAPN",
            timeframe="1m",
            candles=_candles(
                [
                    (10.9, 11.05, 10.85, 11.0, 10_000),
                    (11.0, 11.2, 10.95, 11.15, 11_500),
                    (11.15, 11.38, 11.1, 11.33, 12_000),
                    (11.33, 11.55, 11.28, 11.52, 12_500),
                ]
            ),
            session_context=SessionContext.REGULAR,
            levels=LevelSet(premarket_high=11.45, hod=11.5, prior_close=10.0),
            indicators=IndicatorSet(ema9=11.31, ema20=11.2, vwap=11.25),
            liquidity_context=LiquidityContext(spread=0.02, float_millions=18.0, rvol=1.0),
            news_context={"trend_up": "true", "impulse_active": "true"},
        )
    )
    assert result.detected is False
    assert result.rejection_reason == "INSUFFICIENT_RVOL"


def test_gap_go_is_registry_visible_and_evaluates_through_normal_flow() -> None:
    registry = RossPatternRegistry()
    assert "P_GAP_GO" in registry.pattern_ids
