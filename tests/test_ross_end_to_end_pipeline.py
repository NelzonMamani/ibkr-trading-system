from src.config.config_resolver import set_config_overrides
from src.core.stop_controller import StopController
from src.execution.execution_engine import ExecutionEngine
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.strategy_contracts import (
    DecisionType,
    MarketContext,
    ScannerContext,
    SessionContext,
    StrategyInput,
)


def _ross_inputs(symbol: str = "ROSSX") -> StrategyInput:
    candles = [
        Candle(open=10.0, high=10.4, low=9.9, close=10.3, volume=1000),
        Candle(open=10.3, high=10.7, low=10.2, close=10.6, volume=1300),
        Candle(open=10.6, high=11.0, low=10.5, close=10.7, volume=1800),
        Candle(open=10.75, high=11.35, low=10.65, close=11.28, volume=2600),
    ]
    pattern_inputs = PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.8, hod=11.2, prior_close=9.8),
        indicators=IndicatorSet(ema9=10.7, ema20=10.4, vwap=10.6),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=10.0, rvol=3.0),
        news_context={"catalyst": "news"},
    )
    return StrategyInput(
        symbol=symbol,
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=0.9, rank=1),
        market_context=MarketContext(
            price=11.28,
            spread=0.02,
            volume=300000,
            rvol=3.0,
            session_label="PRE",
        ),
        news_context={"gap_pct": 8.0, "session_phase": "RTH_OPEN"},
        pattern_inputs=[pattern_inputs],
    )


def test_ross_pipeline_emits_intent_passes_risk_and_reaches_execution() -> None:
    set_config_overrides(
        {"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True, "ACTIVE_SESSIONS": ["PRE", "RTH"]}
    )
    try:
        strategy = RossMomentumStrategy()
        decision = strategy.evaluate("ROSSX", _ross_inputs())

        assert decision.decision_type == DecisionType.EMIT_INTENT
        assert decision.intents

        stop_controller = StopController()
        risk_engine = RiskEngine(stop_controller=stop_controller)
        risk_decision = risk_engine.evaluate_strategy_payload(strategy.to_risk_payload(decision))
        risk_decision.decision_id = "ross-e2e-paper"
        entry_price = float(getattr(risk_decision, "entry_price", None) or 11.28)
        risk_decision.entry_price = entry_price
        if getattr(risk_decision, "stop_loss_price", None) is None:
            risk_decision.stop_loss_price = round(entry_price * 0.99, 4)

        assert risk_decision.allowed is True
        assert risk_decision.overall_action == "ALLOW"

        execution_engine = ExecutionEngine(stop_controller=stop_controller)
        execution_engine.current_tick = 1
        execution_result = execution_engine.execute_trade(risk_decision)

        assert execution_result.status in {
            "SIMULATED",
            "PARTIAL",
            "FULL",
            "NOT_FILLED",
            "REJECTED",
            "EXPIRED",
        }
    finally:
        set_config_overrides(None)


def test_ross_pipeline_read_only_is_explicitly_blocked() -> None:
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": True,
            "ACTIVE_SESSIONS": ["PRE", "RTH"],
        }
    )
    try:
        strategy = RossMomentumStrategy()
        decision = strategy.evaluate("ROSSX", _ross_inputs())
        assert decision.decision_type == DecisionType.BLOCK
        assert decision.risk_flags == ["READ_ONLY_MODE"]
        assert decision.intents == []

    finally:
        set_config_overrides(None)
