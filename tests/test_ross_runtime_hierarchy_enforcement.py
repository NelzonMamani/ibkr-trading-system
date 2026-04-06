from __future__ import annotations

from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.strategy_contracts import MarketContext, ScannerContext, SessionContext, StrategyInput


def _setup(
    *,
    name: str,
    family: str,
    confidence: float,
    trigger_type: str,
    trigger_level: float,
    stop_level: float,
) -> PatternResult:
    return PatternResult(
        setup_id=f"P_{family}",
        setup_family_id=family,
        pattern_name=name,
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=[],
        trigger_type=trigger_type,
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=stop_level,
        target_suggestion="2R",
    )


def _inputs(session_label: str = "PRE") -> StrategyInput:
    pattern_inputs = PatternInputs(
        symbol="TEST",
        timeframe="1m",
        candles=[Candle(open=11.0, high=11.6, low=10.9, close=11.5, volume=100_000)],
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=11.0, hod=11.4, prior_close=10.5),
        indicators=IndicatorSet(ema9=11.2, ema20=11.0, vwap=11.1),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=20.0, rvol=3.0),
    )
    return StrategyInput(
        symbol="TEST",
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=0.9, rank=1),
        market_context=MarketContext(
            price=11.5,
            spread=0.02,
            volume=200_000,
            rvol=3.0,
            session_label=session_label,
            key_levels={"PREMARKET_HIGH": 11.0, "PULLBACK_LOW": 10.8, "PULLBACK_HIGH": 11.1},
        ),
        news_context={"session_phase": session_label},
        pattern_inputs=[pattern_inputs],
    )


def test_runtime_pre_uses_gap_go_over_stair_step(monkeypatch, capsys) -> None:
    gap_go = _setup(
        name="Gap & Go",
        family="GAP_GO",
        confidence=0.62,
        trigger_type="GAP_GO_TRIGGER",
        trigger_level=11.0,
        stop_level=10.8,
    )
    stair = _setup(
        name="Trend Continuation (Stair-Step)",
        family="TREND_CONTINUATION_STAIR_STEP",
        confidence=0.95,
        trigger_type="STAIR_STEP_TRIGGER",
        trigger_level=11.2,
        stop_level=11.0,
    )
    summary = PatternEvaluationSummary(
        all_results=[gap_go, stair],
        best_long_setup=stair,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )
    strategy = RossMomentumStrategy()
    monkeypatch.setattr(strategy._evaluator, "evaluate", lambda _inputs: summary)
    monkeypatch.setattr("src.strategies.ross_momentum.strategy._first_valid_fast_trigger", lambda *_args, **_kwargs: None)

    decision = strategy.evaluate("TEST", _inputs("PRE"))

    assert decision.intents
    out = capsys.readouterr().out
    assert "[ROSS][HIERARCHY][SELECTED] symbol=TEST session=PRE setup=GAP_GO" in out
    assert "[ROSS][INTENT_SETUP] symbol=TEST setup_family=GAP_GO" in out


def test_runtime_rth_mid_allows_stair_step_when_higher_tiers_absent(monkeypatch, capsys) -> None:
    stair = _setup(
        name="Trend Continuation (Stair-Step)",
        family="TREND_CONTINUATION_STAIR_STEP",
        confidence=0.71,
        trigger_type="STAIR_STEP_TRIGGER",
        trigger_level=11.0,
        stop_level=10.8,
    )
    summary = PatternEvaluationSummary(
        all_results=[stair],
        best_long_setup=stair,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )
    strategy = RossMomentumStrategy()
    monkeypatch.setattr(strategy._evaluator, "evaluate", lambda _inputs: summary)
    monkeypatch.setattr("src.strategies.ross_momentum.strategy._first_valid_fast_trigger", lambda *_args, **_kwargs: None)

    decision = strategy.evaluate("TEST", _inputs("RTH_MID"))

    assert decision.intents
    out = capsys.readouterr().out
    assert "[ROSS][HIERARCHY][SELECTED] symbol=TEST session=RTH_MID setup=TREND_CONTINUATION_STAIR_STEP" in out
    assert "[ROSS][INTENT_SETUP] symbol=TEST setup_family=TREND_CONTINUATION_STAIR_STEP" in out
