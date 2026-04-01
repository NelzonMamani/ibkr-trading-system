from __future__ import annotations

from src.core.engines.decision_engine import DecisionEngine
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_trend_continuation_stair_step import detect_trend_continuation_stair_step
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs() -> PatternInputs:
    return PatternInputs(
        symbol="PIPE",
        timeframe="1MIN",
        candles=_candles(
            [
                (10.00, 10.12, 9.98, 10.10, 1000),
                (10.10, 10.30, 10.06, 10.25, 1200),
                (10.25, 10.24, 10.12, 10.16, 900),
                (10.16, 10.42, 10.14, 10.38, 1300),
                (10.38, 10.36, 10.24, 10.30, 860),
                (10.30, 10.62, 10.28, 10.58, 1400),
                (10.58, 10.56, 10.34, 10.40, 820),
                (10.40, 10.68, 10.38, 10.66, 1650),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.2, premarket_low=9.8, hod=11.0, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.65, ema20=10.45, vwap=10.5),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=18.0, rvol=1.8),
        news_context={"macd": 0.3},
    )


def test_stair_step_pipeline_pattern_trigger_decision_to_intent() -> None:
    result = detect_trend_continuation_stair_step(_inputs())
    assert result.detected is True

    evaluator = resolve_trigger_evaluator("TREND_CONTINUATION_STAIR_STEP")
    assert evaluator is not None
    trigger = evaluator(
        {
            "setup_family_id": result.setup_family_id,
            "trigger_level": result.trigger_level,
            "stop_level": result.stop_level,
            "invalidation_level": result.invalidation_level,
        },
        {"candles": [*_inputs().candles, Candle(10.66, 10.75, 10.64, 10.74, 1900)], "rvol": 1.8},
    )
    assert trigger["trigger_state"] == "FIRED"

    decision = DecisionEngine().compute_decision(
        symbol="PIPE",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "TREND_CONTINUATION_STAIR_STEP"}],
        pattern_results=[result],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] == "P_TREND_CONTINUATION_STAIR_STEP"

    intent = TradeIntent(
        symbol="PIPE",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=decision["confidence"],
        rationale="stair step breakout",
        trader_type="MOMENTUM",
        decision_id="d-stair-1",
        setup_family_id=decision["selected_setup_family"],
        stop_loss_price=float(result.stop_level or 0.0),
    )
    risk = RiskEngine().evaluate_trade_intent(intent)
    assert risk is not None
    assert risk.reason_code != "PARABOLIC_EXHAUSTION_SUPPRESSION"


def test_stair_step_coexists_with_hod_break_in_decision_pool() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="PIPE",
        levels={},
        structure={"trend": "UP"},
        setups=[
            {"setup_family": "TREND_CONTINUATION_STAIR_STEP"},
            {"setup_family": "HOD_BREAK"},
        ],
        pattern_results=[
            {
                "setup_id": "P_TREND_CONTINUATION_STAIR_STEP",
                "setup_family_id": "TREND_CONTINUATION_STAIR_STEP",
                "pattern_name": "Trend Continuation (Stair-Step)",
                "detected": True,
                "confidence": 0.8,
                "direction": "LONG",
                "trigger_level": 10.60,
                "invalidation_level": 10.24,
                "signal_class": "ENTRY",
            },
            {
                "setup_id": "P_HOD_BREAK",
                "setup_family_id": "HOD_BREAK",
                "pattern_name": "High of Day Break",
                "detected": True,
                "confidence": 0.75,
                "direction": "LONG",
                "trigger_level": 10.62,
                "invalidation_level": 10.30,
            },
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] in {"P_TREND_CONTINUATION_STAIR_STEP", "P_HOD_BREAK"}


def test_stair_step_is_suppressed_when_parabolic_exhaustion_present() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="PIPE",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "TREND_CONTINUATION_STAIR_STEP"}, {"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            {
                "setup_id": "P_TREND_CONTINUATION_STAIR_STEP",
                "setup_family_id": "TREND_CONTINUATION_STAIR_STEP",
                "pattern_name": "Trend Continuation (Stair-Step)",
                "detected": True,
                "confidence": 0.8,
                "direction": "LONG",
                "trigger_level": 10.60,
                "invalidation_level": 10.24,
                "signal_class": "ENTRY",
            },
            {
                "setup_id": "P_PARABOLIC_EXHAUSTION",
                "setup_family_id": "PARABOLIC_EXHAUSTION",
                "pattern_name": "Parabolic Exhaustion",
                "detected": True,
                "confidence": 0.9,
                "direction": "LONG",
                "non_entry_signal": True,
                "signal_class": "RISK_OFF",
                "trigger_mode": "EXIT_SIGNAL",
                "risk_flags": ["EXIT_SIGNAL", "RISK_OFF"],
            },
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None


def test_ross_registry_surfaces_stair_step_through_normal_path() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [p for p in registry.patterns if getattr(p, "pattern_id", "") == "P_TREND_CONTINUATION_STAIR_STEP"]
    results = registry.run(_inputs())
    assert results[0].setup_family_id == "TREND_CONTINUATION_STAIR_STEP"
