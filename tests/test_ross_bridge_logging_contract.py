from types import SimpleNamespace

from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig, build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_trace import PatternInputSnapshotSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import SessionContext


def _inputs() -> PatternInputs:
    return PatternInputs(
        symbol="TEST",
        timeframe="1m",
        candles=[
            Candle(open=10, high=10.3, low=9.9, close=10.2, volume=10000),
            Candle(open=10.2, high=10.4, low=10.1, close=10.35, volume=12000),
        ],
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.4, premarket_low=9.8, hod=10.4, lod=9.8, prior_close=9.7),
        indicators=IndicatorSet(ema9=10.2, ema20=10.0, vwap=10.1),
        liquidity_context=LiquidityContext(spread=0.03, float_millions=5.0, rvol=2.0),
    )


def test_pattern_input_summary_contract_is_non_empty() -> None:
    summary = PatternInputSnapshotSummary(
        candle_count=2,
        last_price=10.35,
        bid=10.34,
        ask=10.37,
        spread=0.03,
        spread_pct=0.28,
        volume=22000,
        pct_change=6.7,
        gap_pct=4.3,
        rvol=2.0,
        float_millions=5.0,
        has_levels=True,
        levels_present=["premarket_high", "premarket_low"],
        has_indicators=True,
        indicators_present=["EMA9", "EMA20", "VWAP"],
        session_context="PRE",
        timeframe="1m",
        quality_flags=[],
        missing_fields=[],
    )
    payload = summary.to_dict()
    assert payload
    assert payload["spread_pct"] == 0.28
    assert payload["gap_pct"] == 4.3


def test_pattern_registry_logs_missing_inputs(capsys) -> None:
    registry = RossPatternRegistry()
    registry.run(
        _inputs(),
        trace_context={"input_summary": {"missing_fields": ["bid", "ask"], "candle_count": 2}},
    )
    out = capsys.readouterr().out
    assert "[PATTERN_TRACE][INPUT_MISSING] symbol=TEST" in out


def test_strategy_trace_precheck_fields_are_truthful(capsys) -> None:
    setup = SimpleNamespace(
        detected=True,
        confidence=0.92,
        entry_zone="break_above_premarket_high",
        risk_flags=["WARN_ONLY"],
        data_quality_flags=[],
        direction=Direction.LONG,
        pattern_name="P_GAP_GO",
        stop_suggestion="pm_low",
        target_suggestion="2R",
        rationale_text="trigger fired",
    )
    summary = SimpleNamespace(
        conflict_flag=False,
        best_long_setup=setup,
        best_short_setup=None,
        all_results=[setup],
        veto_flags=["ACCOUNT_RISK_LIMIT"],
    )

    build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=summary,
        config=IntentPolicyConfig(min_confidence=0.6),
    )

    out = capsys.readouterr().out
    assert "risk_precheck_ok=False" in out
    assert "execution_candidate_ready=False" in out
    assert "risk_ok=" not in out
