from types import SimpleNamespace

from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig, build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_types import Direction


def test_trigger_and_confirmation_always_create_intent_even_when_risk_blocked(capsys) -> None:
    setup = SimpleNamespace(
        detected=True,
        confidence=0.92,
        entry_zone="break_above_premarket_high",
        risk_flags=["MAX_RISK_PER_TRADE_EXCEEDED"],
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

    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=summary,
        config=IntentPolicyConfig(min_confidence=0.6),
    )

    assert len(intents) == 1
    assert intents[0].symbol == "TEST"
    assert intents[0].entry_model == "break_above_premarket_high"
    out = capsys.readouterr().out
    assert "[INTENT][CREATE] symbol=TEST" in out
    assert "trigger=TRUE" in out
