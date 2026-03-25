from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import DecisionType, MarketContext, ScannerContext, SessionContext, StrategyInput


def _inputs(*, final_high: float, final_low: float, final_close: float, rvol: float, pct_change: float) -> StrategyInput:
    pattern_inputs = PatternInputs(
        symbol="FAST",
        timeframe="1m",
        candles=[
            Candle(open=10.0, high=10.3, low=9.9, close=10.25, volume=2200),
            Candle(open=10.25, high=10.5, low=10.2, close=10.45, volume=3200),
            Candle(open=10.45, high=10.48, low=10.28, close=10.32, volume=1500),
            Candle(open=10.32, high=final_high, low=final_low, close=final_close, volume=2100),
        ],
        session_context=SessionContext.PRE,
        levels=LevelSet(
            premarket_high=10.25,
            hod=10.50,
            prior_close=9.8,
            key_levels={"PULLBACK_HIGH": 10.48},
        ),
        indicators=IndicatorSet(ema9=10.3, ema20=10.15, vwap=10.2),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=rvol),
    )
    return StrategyInput(
        symbol="FAST",
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=1.0, rank=1),
        market_context=MarketContext(
            price=final_close,
            spread=0.02,
            volume=350000,
            rvol=rvol,
            session_label="PRE",
            key_levels={"HOD": 10.50, "PREMARKET_HIGH": 10.25, "PULLBACK_HIGH": 10.48},
        ),
        news_context={"pct_change": pct_change, "gap_pct": pct_change, "session_phase": "RTH_OPEN"},
        pattern_inputs=[pattern_inputs],
    )


def test_first_new_high_trigger_emits_intent_and_logs(capsys) -> None:
    strategy = RossMomentumStrategy()
    decision = strategy.evaluate("FAST", _inputs(final_high=10.56, final_low=10.3, final_close=10.53, rvol=2.4, pct_change=7.0))
    captured = capsys.readouterr().out

    assert "[ROSS][TRIGGER][RESULT]" in captured
    assert "trigger_name=FIRST_NEW_HIGH_AFTER_PULLBACK" in captured
    assert decision.decision_type == DecisionType.EMIT_INTENT
    assert decision.intents


def test_no_trigger_path_emits_explicit_no_signal(capsys) -> None:
    strategy = RossMomentumStrategy()
    decision = strategy.evaluate("FAST", _inputs(final_high=10.47, final_low=10.3, final_close=10.4, rvol=2.0, pct_change=6.0))
    captured = capsys.readouterr().out

    assert "[ROSS][NO_SIGNAL]" in captured
    assert "stage=TRIGGER" in captured
    assert decision.decision_type in {DecisionType.WATCH, DecisionType.NO_ACTION}
