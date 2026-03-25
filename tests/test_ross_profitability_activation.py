from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.strategy_contracts import (
    DecisionType,
    MarketContext,
    ScannerContext,
    SessionContext,
    StrategyInput,
)


def _inputs(
    symbol: str = "ROSSX",
    session: str = "PRE",
    spread: float = 0.02,
    rvol: float = 3.0,
    price: float = 11.5,
) -> StrategyInput:
    return StrategyInput(
        symbol=symbol,
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=0.9, rank=1),
        market_context=MarketContext(
            price=price,
            spread=spread,
            volume=250000,
            rvol=rvol,
            session_label=session,
            key_levels={
                "PREMARKET_HIGH": 11.2,
                "PREMARKET_LOW": 10.8,
                "HOD": 11.4,
                "PULLBACK_HIGH": 11.0,
                "PULLBACK_LOW": 10.9,
                "MICRO_PULLBACK_HIGH": 11.1,
                "MICRO_PULLBACK_LOW": 10.95,
            },
        ),
        news_context={"gap_pct": 9.0, "session_phase": session},
        pattern_inputs=[
            PatternInputs(
                symbol=symbol,
                timeframe="1m",
                candles=[
                    Candle(open=10.0, high=10.6, low=9.9, close=10.5, volume=1000),
                    Candle(open=10.5, high=11.0, low=10.4, close=10.9, volume=1400),
                ],
                session_context=SessionContext.PRE,
                levels=LevelSet(premarket_high=11.2, hod=11.4, prior_close=9.8),
                indicators=IndicatorSet(ema9=10.7, ema20=10.4, vwap=10.6),
                liquidity_context=LiquidityContext(spread=spread, float_millions=10.0, rvol=rvol),
            )
        ],
    )


def _summary(pattern_name: str, detected: bool = True, confidence: float = 0.8) -> PatternEvaluationSummary:
    result = PatternResult(
        setup_id=pattern_name,
        pattern_name=pattern_name,
        pattern_family=PatternFamily.BREAKOUT,
        detected=detected,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=["K_VOLUME_CONFIRM"],
        stop_suggestion="below structure",
        rejection_reason=None if detected else "not_detected",
    )
    return PatternEvaluationSummary(
        all_results=[result],
        best_long_setup=result if detected else None,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )


def test_case_a_premarket_high_break_emits_intent(capsys) -> None:
    strategy = RossMomentumStrategy()
    strategy._evaluator.evaluate = lambda *_: _summary("PREMARKET_HIGH_BREAK")  # type: ignore[assignment]
    decision = strategy.evaluate("ROSSA", _inputs("ROSSA", "PRE"))
    out = capsys.readouterr().out
    assert decision.decision_type == DecisionType.EMIT_INTENT
    assert decision.intents
    assert "[ROSS][PATTERN][START]" in out
    assert "[ROSS][TRIGGER][RESULT]" in out
    assert "[ROSS][INTENT][CREATED]" in out


def test_case_b_first_pullback_emits_intent() -> None:
    strategy = RossMomentumStrategy()
    strategy._evaluator.evaluate = lambda *_: _summary("FIRST_PULLBACK")  # type: ignore[assignment]
    decision = strategy.evaluate("ROSSB", _inputs("ROSSB", "RTH_OPEN"))
    assert decision.decision_type == DecisionType.EMIT_INTENT
    assert decision.intents


def test_case_c_micro_pullback_emits_intent() -> None:
    strategy = RossMomentumStrategy()
    strategy._evaluator.evaluate = lambda *_: _summary("MICRO_PULLBACK")  # type: ignore[assignment]
    decision = strategy.evaluate("ROSSC", _inputs("ROSSC", "RTH_OPEN"))
    assert decision.decision_type == DecisionType.EMIT_INTENT
    assert decision.intents


def test_case_d_pattern_valid_but_trigger_not_fired_logs_no_signal(capsys) -> None:
    strategy = RossMomentumStrategy()
    strategy._evaluator.evaluate = lambda *_: _summary("FIRST_PULLBACK")  # type: ignore[assignment]
    bad_inputs = _inputs("ROSSD", "PRE", rvol=3.0, price=10.95)
    bad_inputs.market_context.key_levels.pop("PULLBACK_LOW")
    bad_inputs.market_context.key_levels.pop("MICRO_PULLBACK_LOW")
    bad_inputs.market_context.key_levels["PULLBACK_HIGH"] = 12.0
    decision = strategy.evaluate("ROSSD", bad_inputs)
    out = capsys.readouterr().out
    assert decision.decision_type in {DecisionType.WATCH, DecisionType.NO_ACTION}
    assert "[ROSS][TRIGGER][REJECT]" in out
    assert "[ROSS][END_TO_END][NO_SIGNAL]" in out


def test_case_e_trigger_fires_and_risk_layer_can_block(capsys) -> None:
    strategy = RossMomentumStrategy()
    strategy._evaluator.evaluate = lambda *_: _summary("HOD_BREAK")  # type: ignore[assignment]
    blocked_inputs = _inputs("ROSSE", "RTH_MID", spread=0.5)
    decision = strategy.evaluate("ROSSE", blocked_inputs)
    out = capsys.readouterr().out
    assert decision.intents == []
    assert "[ROSS][CONFIRM][BLOCK]" in out
    assert "BLOCKED_AT_CONFIRMATION" in out
