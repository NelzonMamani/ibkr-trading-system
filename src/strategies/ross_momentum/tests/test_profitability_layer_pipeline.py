from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.pattern_engine import PatternEngine
from src.strategies.ross_momentum.setup_engine import SetupEngine
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.ross_momentum.trigger_engine import TriggerEngine
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import DecisionType, MarketContext, ScannerContext, SessionContext, StrategyInput


def _pattern_input(candles: list[Candle]) -> PatternInputs:
    return PatternInputs(
        symbol="RM",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=LevelSet(
            premarket_high=10.4,
            hod=10.5,
            prior_close=9.9,
            key_levels={"PULLBACK_HIGH": 10.25},
        ),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.15),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=18.0, rvol=2.5),
    )


def _strategy_input(candles: list[Candle], *, price: float, gap_pct: float = 7.0) -> StrategyInput:
    return StrategyInput(
        symbol="RM",
        session_context=SessionContext.PRE,
        scanner_context=ScannerContext(score=1.0, rank=1),
        market_context=MarketContext(
            price=price,
            spread=0.02,
            volume=450000,
            rvol=2.5,
            session_label="PRE",
            key_levels={"HOD": 10.5, "PREMARKET_HIGH": 10.4, "PULLBACK_HIGH": 10.25},
        ),
        news_context={"gap_pct": gap_pct, "pct_change": gap_pct, "session_phase": "RTH_OPEN"},
        pattern_inputs=[_pattern_input(candles)],
    )


def test_setup_family_detects_first_pullback_context() -> None:
    candles = [
        Candle(10.0, 10.25, 9.95, 10.2, 3000),
        Candle(10.2, 10.45, 10.12, 10.4, 5000),
        Candle(10.4, 10.42, 10.22, 10.28, 2200),
        Candle(10.28, 10.46, 10.26, 10.44, 2600),
    ]
    setup = SetupEngine().classify("RM", _pattern_input(candles), _strategy_input(candles, price=10.44).market_context, {"gap_pct": 7.0, "session_phase": "RTH_OPEN"})
    assert setup.detected
    assert setup.setup_family in {"GAP_AND_GO", "FIRST_PULLBACK", "MICRO_PULLBACK", "PREMARKET_HIGH_BREAK"}


def test_setup_family_none_for_invalid_context() -> None:
    candles = [
        Candle(10.0, 10.01, 9.95, 9.98, 800),
        Candle(9.98, 10.0, 9.9, 9.92, 750),
    ]
    setup = SetupEngine().classify("RM", _pattern_input(candles), _strategy_input(candles, price=9.92, gap_pct=0.0).market_context, {"gap_pct": 0.0, "session_phase": "PRE"})
    assert not setup.detected
    assert setup.setup_family == "NONE"


def test_pattern_stage_valid_and_has_invalidation_anchor() -> None:
    candles = [
        Candle(10.0, 10.2, 9.95, 10.18, 4000),
        Candle(10.18, 10.4, 10.15, 10.35, 4300),
        Candle(10.35, 10.38, 10.22, 10.25, 1800),
        Candle(10.25, 10.45, 10.24, 10.42, 2500),
    ]
    setup = SetupEngine().classify("RM", _pattern_input(candles), _strategy_input(candles, price=10.42).market_context, {"gap_pct": 7.0, "session_phase": "RTH_OPEN"})
    pattern = PatternEngine().evaluate(setup, _pattern_input(candles))
    assert pattern.detected
    assert pattern.invalidation_ready
    assert pattern.pullback_low is not None


def test_pattern_stage_rejects_structure_failure_and_missing_anchor() -> None:
    candles = [
        Candle(10.0, 10.3, 9.98, 10.25, 5000),
        Candle(10.25, 10.35, 10.2, 10.22, 4800),
        Candle(10.22, 10.24, 9.8, 9.9, 7000),
        Candle(9.9, 10.0, 9.7, 9.75, 6800),
    ]
    setup = SetupEngine().classify("RM", _pattern_input(candles), _strategy_input(candles, price=9.75, gap_pct=0.0).market_context, {"gap_pct": 0.0, "session_phase": "RTH_OPEN"})
    pattern = PatternEngine().evaluate(setup, _pattern_input(candles))
    assert not pattern.detected
    assert pattern.rejection_reason in {"STRUCTURE_FAILURE", "NO_SETUP_FAMILY", "PULLBACK_VOLUME_TOO_HEAVY"}


def test_trigger_stage_first_new_high_fire_and_reject_paths() -> None:
    trigger_engine = TriggerEngine()
    valid_pattern = PatternEngine().evaluate(
        SetupEngine().classify(
            "RM",
            _pattern_input([
                Candle(10.0, 10.2, 9.95, 10.18, 4000),
                Candle(10.18, 10.4, 10.15, 10.35, 4300),
                Candle(10.35, 10.38, 10.22, 10.25, 1800),
                Candle(10.25, 10.45, 10.24, 10.42, 2500),
            ]),
            _strategy_input([
                Candle(10.0, 10.2, 9.95, 10.18, 4000),
                Candle(10.18, 10.4, 10.15, 10.35, 4300),
                Candle(10.35, 10.38, 10.22, 10.25, 1800),
                Candle(10.25, 10.45, 10.24, 10.42, 2500),
            ], price=10.42).market_context,
            {"gap_pct": 7.0, "session_phase": "RTH_OPEN"},
        ),
        _pattern_input([
            Candle(10.0, 10.2, 9.95, 10.18, 4000),
            Candle(10.18, 10.4, 10.15, 10.35, 4300),
            Candle(10.35, 10.38, 10.22, 10.25, 1800),
            Candle(10.25, 10.45, 10.24, 10.42, 2500),
        ]),
    )
    fired = trigger_engine.evaluate(valid_pattern, Candle(10.42, 10.5, 10.35, 10.48, 2600))
    not_fired = trigger_engine.evaluate(valid_pattern, Candle(10.42, 10.37, 10.3, 10.33, 2000))
    invalidated = trigger_engine.evaluate(valid_pattern, Candle(10.3, 10.5, 10.1, 10.45, 2700))

    assert fired.triggered
    assert not not_fired.triggered
    assert not_fired.rejection_reason == "HIGH_NOT_ABOVE_PULLBACK_HIGH"
    assert not invalidated.triggered
    assert invalidated.rejection_reason == "INVALIDATION_BROKEN"


def test_pipeline_end_to_end_intent_and_no_signal_paths(capsys) -> None:
    strategy = RossMomentumStrategy()
    valid = [
        Candle(10.0, 10.2, 9.95, 10.18, 4000),
        Candle(10.18, 10.4, 10.15, 10.35, 4300),
        Candle(10.35, 10.38, 10.22, 10.25, 1800),
        Candle(10.25, 10.45, 10.24, 10.42, 2500),
    ]
    decision_ok = strategy.evaluate("RM", _strategy_input(valid, price=10.42))
    assert decision_ok.decision_type == DecisionType.EMIT_INTENT
    assert decision_ok.intents

    no_pattern = [
        Candle(10.0, 10.1, 9.95, 10.0, 4000),
        Candle(10.0, 10.02, 9.8, 9.85, 7000),
        Candle(9.85, 9.9, 9.6, 9.7, 7600),
        Candle(9.7, 9.8, 9.5, 9.55, 7400),
    ]
    decision_no_pattern = strategy.evaluate("RM", _strategy_input(no_pattern, price=9.55, gap_pct=0.0))
    assert decision_no_pattern.decision_type in {DecisionType.NO_ACTION, DecisionType.WATCH}

    no_trigger = [
        Candle(10.0, 10.2, 9.95, 10.18, 4200),
        Candle(10.18, 10.4, 10.15, 10.35, 4500),
        Candle(10.35, 10.38, 10.22, 10.25, 1500),
        Candle(10.25, 10.37, 10.24, 10.3, 1600),
    ]
    decision_no_trigger = strategy.evaluate("RM", _strategy_input(no_trigger, price=10.3))
    assert decision_no_trigger.decision_type in {DecisionType.NO_ACTION, DecisionType.WATCH}

    out = capsys.readouterr().out
    assert "[ROSS][INTENT][CREATED]" in out
    assert "[ROSS][NO_SIGNAL]" in out
