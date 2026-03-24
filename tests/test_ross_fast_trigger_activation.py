from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import DecisionType, MarketContext, ScannerContext, SessionContext, StrategyInput


def _inputs(*, price: float, rvol: float, pct_change: float) -> StrategyInput:
    pattern_inputs = PatternInputs(
        symbol="FAST",
        timeframe="1m",
        candles=[
            Candle(open=10.0, high=10.3, low=9.9, close=10.2, volume=1000),
            Candle(open=10.2, high=10.4, low=10.1, close=10.35, volume=1300),
        ],
        session_context=SessionContext.PRE,
        levels=LevelSet(
            premarket_high=10.25,
            hod=10.30,
            prior_close=9.8,
            key_levels={"PULLBACK_HIGH": 10.22},
        ),
        indicators=IndicatorSet(ema9=10.1, ema20=10.0, vwap=10.05),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=rvol),
    )
    return StrategyInput(
        symbol="FAST",
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=1.0, rank=1),
        market_context=MarketContext(
            price=price,
            spread=0.02,
            volume=350000,
            rvol=rvol,
            session_label="PRE",
            key_levels={"HOD": 10.30, "PREMARKET_HIGH": 10.25, "PULLBACK_HIGH": 10.22},
        ),
        news_context={"pct_change": pct_change, "gap_pct": pct_change, "session_phase": "RTH_OPEN"},
        pattern_inputs=[pattern_inputs],
    )


def test_fast_trigger_emits_ross_trigger_log_and_intent(capsys) -> None:
    strategy = RossMomentumStrategy()
    decision = strategy.evaluate("FAST", _inputs(price=10.33, rvol=2.4, pct_change=7.0))
    captured = capsys.readouterr().out

    assert "[ROSS][TRIGGER]" in captured
    assert "trigger_type=HOD_BREAK_FAST" in captured
    assert decision.decision_type == DecisionType.EMIT_INTENT
    assert decision.intents


def test_high_momentum_override_emits_override_log(capsys) -> None:
    strategy = RossMomentumStrategy()
    decision = strategy.evaluate("FAST", _inputs(price=10.35, rvol=2.8, pct_change=11.0))
    captured = capsys.readouterr().out

    assert "[ROSS][TRIGGER_OVERRIDE] reason=HIGH_MOMENTUM_BREAK" in captured
    assert decision.decision_type == DecisionType.EMIT_INTENT
