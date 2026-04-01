from __future__ import annotations

from src.core.engines.decision_engine import DecisionEngine
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs() -> PatternInputs:
    return PatternInputs(
        symbol="BFLG",
        timeframe="1MIN",
        candles=_candles(
            [
                (10.00, 10.20, 9.99, 10.18, 1300),
                (10.18, 10.45, 10.16, 10.42, 1600),
                (10.42, 10.80, 10.40, 10.76, 2000),
                (10.76, 10.79, 10.68, 10.72, 1200),
                (10.72, 10.75, 10.66, 10.70, 980),
                (10.70, 10.73, 10.64, 10.68, 900),
                (10.68, 10.71, 10.63, 10.69, 860),
                (10.69, 10.72, 10.65, 10.70, 840),
                (10.70, 10.90, 10.69, 10.88, 2100),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.25, premarket_low=9.82, hod=10.90, lod=9.82, prior_close=9.95),
        indicators=IndicatorSet(ema9=10.72, ema20=10.55, vwap=10.62),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=15.0, rvol=1.7),
    )


def test_bull_flag_pipeline_end_to_end() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [p for p in registry.patterns if getattr(p, "pattern_id", "") == "P_BULL_FLAG"]
    pattern = registry.run(_inputs())[0]
    assert pattern.detected is True
    assert pattern.setup_family_id == "BULL_FLAG"
    assert pattern.trigger_type == "BULL_FLAG_BREAKOUT"
    assert pattern.trigger_mode == "BREAKOUT_CONTINUATION"
    assert pattern.signal_class == "ENTRY"

    evaluator = resolve_trigger_evaluator("BULL_FLAG")
    assert evaluator is not None
    trigger = evaluator(
        {
            "setup_family_id": pattern.setup_family_id,
            "trigger_level": pattern.trigger_level,
            "stop_level": pattern.stop_level,
            "invalidation_level": pattern.invalidation_level,
        },
        {"candles": _inputs().candles, "rvol": 1.7, "spread": 0.02},
    )
    assert trigger["trigger_state"] == "FIRED"

    decision = DecisionEngine().compute_decision(
        symbol="BFLG",
        levels={},
        structure={"trend": "UP"},
        setups=[
            {"setup_family": "BULL_FLAG"},
            {"setup_family": "EMA_PULLBACK"},
            {"setup_family": "VWAP_PULLBACK"},
            {"setup_family": "TREND_CONTINUATION_STAIR_STEP"},
        ],
        pattern_results=[pattern],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] in {
        "P_BULL_FLAG",
        "P_EMA_PULLBACK",
        "P_VWAP_PULLBACK",
        "P_TREND_CONTINUATION_STAIR_STEP",
    }

    intent = TradeIntent(
        symbol="BFLG",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=decision["confidence"],
        rationale="bull flag breakout continuation",
        trader_type="MOMENTUM",
        decision_id="d-bf-1",
        setup_family_id=decision["selected_setup_family"],
        stop_loss_price=float(pattern.stop_level or 0.0),
    )
    risk = RiskEngine().evaluate_trade_intent(intent)
    assert risk is not None
    assert intent.stop_loss_price is not None
