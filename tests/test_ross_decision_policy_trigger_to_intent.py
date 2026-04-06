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


def test_hierarchy_blocks_lower_tier_even_with_higher_confidence(capsys) -> None:
    high_tier = SimpleNamespace(
        detected=True,
        confidence=0.65,
        entry_zone="gap_break",
        risk_flags=[],
        data_quality_flags=[],
        direction=Direction.LONG,
        pattern_name="GAP_GO",
        stop_suggestion="pm_low",
        target_suggestion="2R",
        rationale_text="gap go setup",
    )
    lower_tier = SimpleNamespace(
        detected=True,
        confidence=0.95,
        entry_zone="stair_step_break",
        risk_flags=[],
        data_quality_flags=[],
        direction=Direction.LONG,
        pattern_name="TREND_CONTINUATION_STAIR_STEP",
        stop_suggestion="last_higher_low",
        target_suggestion="2R",
        rationale_text="stair step setup",
    )
    summary = SimpleNamespace(
        conflict_flag=False,
        best_long_setup=lower_tier,
        best_short_setup=None,
        all_results=[lower_tier, high_tier],
        veto_flags=[],
    )

    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=summary,
        config=IntentPolicyConfig(min_confidence=0.6),
        session="RTH_OPEN",
    )

    assert len(intents) == 1
    assert "GAP_GO" in intents[0].intent_id
    out = capsys.readouterr().out
    assert "[ROSS][HIERARCHY]" in out
    assert "selected=GAP_GO" in out


def test_invalid_session_is_blocked_before_intent_creation(capsys) -> None:
    setup = SimpleNamespace(
        detected=True,
        confidence=0.9,
        entry_zone="breakout",
        risk_flags=[],
        data_quality_flags=[],
        direction=Direction.LONG,
        pattern_name="GAP_GO",
        stop_suggestion="pm_low",
        target_suggestion="2R",
        rationale_text="valid setup",
    )
    summary = SimpleNamespace(
        conflict_flag=False,
        best_long_setup=setup,
        best_short_setup=None,
        all_results=[setup],
        veto_flags=[],
    )

    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=summary,
        session="OVN",
    )

    assert intents == []
    out = capsys.readouterr().out
    assert "blocker=SESSION_INVALID" in out
