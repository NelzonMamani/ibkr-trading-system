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


def test_invalid_session_allows_intent_when_validation_override_enabled(capsys) -> None:
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
        session="AH",
        config=IntentPolicyConfig(validation_session_override=True),
    )

    assert len(intents) == 1
    assert intents[0].validation_override is True
    out = capsys.readouterr().out
    assert "[ROSS][SESSION_OVERRIDE] symbol=TEST session=AH" in out
    assert "[INTENT][OVERRIDE] symbol=TEST session=AH reason=SESSION_OVERRIDE" in out


def _after_hours_summary(pattern_name: str = "MICRO_PULLBACK"):
    setup = SimpleNamespace(
        detected=True,
        confidence=0.9,
        entry_zone="breakout",
        risk_flags=[],
        data_quality_flags=[],
        direction=Direction.LONG,
        pattern_name=pattern_name,
        stop_suggestion="pm_low",
        target_suggestion="2R",
        rationale_text="valid setup",
    )
    return SimpleNamespace(
        conflict_flag=False,
        best_long_setup=setup,
        best_short_setup=None,
        all_results=[setup],
        veto_flags=[],
    )


def test_after_hours_paper_flag_off_blocks_intent(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.delenv("ALLOW_PAPER_AFTER_HOURS_INTENTS", raising=False)
    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=_after_hours_summary(),
        session="AFTER",
        trigger_ready_now=True,
    )
    assert intents == []
    out = capsys.readouterr().out
    assert "decision=BLOCK block_reason=BLOCKED_BY_POLICY session=AFTER" in out


def test_after_hours_paper_flag_on_allowed_setup_creates_intent(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("ALLOW_PAPER_AFTER_HOURS_INTENTS", "true")
    monkeypatch.setenv("PAPER_AFTER_HOURS_ALLOWED_SETUPS", "MICRO_PULLBACK,FLAT_TOP_BREAKOUT")
    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=_after_hours_summary("MICRO_PULLBACK"),
        session="AFTER",
        trigger_ready_now=True,
    )
    assert len(intents) == 1
    out = capsys.readouterr().out
    assert "[ROSS][SESSION_POLICY_OVERRIDE] symbol=TEST mode=PAPER session=AFTER setup=MICRO_PULLBACK" in out
    assert "decision=ALLOW block_reason=NONE session=AFTER override=paper_after_hours_validation" in out


def test_after_hours_live_remains_blocked_even_when_flag_on(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RUN_MODE", "LIVE")
    monkeypatch.setenv("ALLOW_PAPER_AFTER_HOURS_INTENTS", "true")
    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=_after_hours_summary("MICRO_PULLBACK"),
        session="AFTER",
        trigger_ready_now=True,
    )
    assert intents == []
    out = capsys.readouterr().out
    assert "blocker=SESSION_INVALID reason=AH_LIVE_POLICY" in out
    assert "decision=BLOCK block_reason=BLOCKED_BY_POLICY session=AFTER" in out


def test_regular_session_behavior_unchanged_with_paper_after_hours_flag(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("ALLOW_PAPER_AFTER_HOURS_INTENTS", "true")
    intents = build_trade_intents(
        strategy_id="RossMomentumStrategyV1",
        symbol="TEST",
        summary=_after_hours_summary("GAP_GO"),
        session="RTH_OPEN",
        trigger_ready_now=True,
    )
    assert len(intents) == 1
    out = capsys.readouterr().out
    assert "SESSION_POLICY_OVERRIDE" not in out
