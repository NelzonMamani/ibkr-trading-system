from __future__ import annotations

from src.core.engines.decision_engine import DecisionEngine
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_vwap_pullback import detect_vwap_pullback
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs() -> PatternInputs:
    return PatternInputs(
        symbol="VPIP",
        timeframe="1MIN",
        candles=_candles(
            [
                (10.00, 10.08, 9.98, 10.06, 900),
                (10.06, 10.24, 10.04, 10.22, 1100),
                (10.22, 10.54, 10.20, 10.50, 1650),
                (10.50, 10.56, 10.30, 10.33, 900),
                (10.33, 10.38, 10.29, 10.34, 850),
                (10.34, 10.58, 10.33, 10.52, 1500),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.8, premarket_low=9.9, hod=10.9, prior_close=10.0),
        indicators=IndicatorSet(ema9=10.48, ema20=10.32, vwap=10.35),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=1.8),
        news_context={"macd": 0.4},
    )


def test_vwap_pullback_pipeline_pattern_trigger_decision_to_intent() -> None:
    result = detect_vwap_pullback(_inputs())
    assert result.detected is True

    evaluator = resolve_trigger_evaluator("VWAP_PULLBACK")
    assert evaluator is not None
    trigger = evaluator(
        {
            "setup_family_id": result.setup_family_id,
            "trigger_level": result.trigger_level,
            "stop_level": result.stop_level,
            "invalidation_level": result.invalidation_level,
        },
        {"candles": [*_inputs().candles, Candle(10.52, 10.68, 10.50, 10.64, 1900)], "rvol": 1.8},
    )
    assert trigger["trigger_state"] == "FIRED"

    decision = DecisionEngine().compute_decision(
        symbol="VPIP",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "VWAP_PULLBACK"}],
        pattern_results=[result],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] == "P_VWAP_PULLBACK"

    intent = TradeIntent(
        symbol="VPIP",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=decision["confidence"],
        rationale="vwap pullback continuation",
        trader_type="MOMENTUM",
        decision_id="d-vwap-1",
        setup_family_id=decision["selected_setup_family"],
        stop_loss_price=float(result.stop_level or 0.0),
    )
    risk = RiskEngine().evaluate_trade_intent(intent)
    assert risk is not None
    assert risk.reason_code != "PARABOLIC_EXHAUSTION_SUPPRESSION"


def test_vwap_pullback_coexists_with_hod_break_and_stair_step() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="VPIP",
        levels={},
        structure={"trend": "UP"},
        setups=[
            {"setup_family": "VWAP_PULLBACK"},
            {"setup_family": "HOD_BREAK"},
            {"setup_family": "TREND_CONTINUATION_STAIR_STEP"},
        ],
        pattern_results=[
            {"setup_id": "P_VWAP_PULLBACK", "setup_family_id": "VWAP_PULLBACK", "detected": True, "confidence": 0.81, "direction": "LONG"},
            {"setup_id": "P_HOD_BREAK", "setup_family_id": "HOD_BREAK", "detected": True, "confidence": 0.75, "direction": "LONG"},
            {"setup_id": "P_TREND_CONTINUATION_STAIR_STEP", "setup_family_id": "TREND_CONTINUATION_STAIR_STEP", "detected": True, "confidence": 0.72, "direction": "LONG"},
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] in {"P_VWAP_PULLBACK", "P_HOD_BREAK", "P_TREND_CONTINUATION_STAIR_STEP"}


def test_vwap_pullback_suppressed_when_parabolic_exhaustion_present() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="VPIP",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "VWAP_PULLBACK"}, {"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            {"setup_id": "P_VWAP_PULLBACK", "setup_family_id": "VWAP_PULLBACK", "detected": True, "confidence": 0.8, "direction": "LONG", "signal_class": "ENTRY"},
            {
                "setup_id": "P_PARABOLIC_EXHAUSTION",
                "setup_family_id": "PARABOLIC_EXHAUSTION",
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


def test_ross_registry_surfaces_vwap_pullback_through_normal_path() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [p for p in registry.patterns if getattr(p, "pattern_id", "") == "P_VWAP_PULLBACK"]
    results = registry.run(_inputs())
    assert results[0].setup_family_id == "VWAP_PULLBACK"
