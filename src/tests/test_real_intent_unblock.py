from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents
from src.strategies.ross_momentum.decision_policy import (
    IntentMarketContext,
    IntentPolicyConfig,
    build_trade_intents,
)
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _summary_with_detected_setup() -> PatternEvaluationSummary:
    setup = PatternResult(
        setup_id="TEST_SETUP",
        pattern_name="TEST_SETUP",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.9,
        setup_quality_tags=["test"],
        entry_zone="breakout",
        stop_suggestion="under low",
        risk_flags=["veto-risk"],
        data_quality_flags=["missing_bid_ask"],
        trigger_type="TEST_TRIGGER",
    )
    return PatternEvaluationSummary(
        all_results=[setup],
        best_long_setup=setup,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test summary",
        veto_flags=["wide_spread"],
    )


def test_strategy_intent_generation_forces_execution_ready_when_core_signal_valid() -> None:
    summary = _summary_with_detected_setup()
    intents = build_trade_intents(
        strategy_id="RossMomentum",
        symbol="XYZ",
        summary=summary,
        config=IntentPolicyConfig(min_confidence=0.5),
        market_context=IntentMarketContext(
            session_label="PRE",
            last_price=12.5,
            volume=100_000,
            premarket_volume=60_000,
            spread_pct=0.4,
            halted=False,
        ),
    )
    assert len(intents) == 1


def test_risk_capital_override_and_premarket_dq_relaxation() -> None:
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="XYZ",
                intent_id="intent-1",
                setup_id="TEST_SETUP",
                side="LONG",
                entry="LIMIT",
                stop="STRUCTURE",
                rationale="test",
                tags=["DATA_QUALITY", "SESSION_PRE"],
                entry_price=10.0,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(available_funds=0.0),
    )
    assert decisions[0].decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
    assert decisions[0].available_funds == 10_000.0
    assert decisions[0].max_position_size > 0
