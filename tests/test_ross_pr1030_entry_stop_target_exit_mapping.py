from __future__ import annotations

from src.strategies.ross_momentum.certification.e2e_harness import (
    build_pr6_positive_cases,
    run_ross_e2e_case,
)
from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig, build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.strategy_contracts import Direction as IntentDirection
from src.strategies.strategy_contracts import TimeInForcePolicy


_STRATEGY_ID = "RossMomentumStrategyV1"


def _summary_with(setup: PatternResult) -> PatternEvaluationSummary:
    return PatternEvaluationSummary(
        all_results=[setup],
        best_long_setup=setup if setup.direction == Direction.LONG else None,
        best_short_setup=setup if setup.direction == Direction.SHORT else None,
        conflict_flag=False,
        combined_rationale_text="PR1030 mapping test",
        veto_flags=[],
    )


def _entry_setup(
    *,
    pattern_name: str = "Micro Pullback",
    setup_id: str = "P_MICRO_PULLBACK",
    setup_family_id: str = "MICRO_PULLBACK",
    trigger_level: float | None = 10.50,
    stop_level: float | None = 10.18,
    target_suggestion: str | None = "Prior high / HOD extension",
    d_projection: float | None = None,
    non_entry_signal: bool = False,
    signal_class: str | None = None,
    trigger_mode: str | None = None,
    direction: Direction = Direction.LONG,
) -> PatternResult:
    return PatternResult(
        setup_id=setup_id,
        setup_family_id=setup_family_id,
        pattern_name=pattern_name,
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=direction,
        confidence=0.82,
        setup_quality_tags=["pr1030_fixture"],
        entry_zone="Break of mapped trigger",
        stop_suggestion="Below mapped structure low",
        target_suggestion=target_suggestion,
        rationale_text="PR1030 fixture has complete Ross price-action mapping.",
        trigger_type="XL_PR1030_TEST",
        trigger_level=trigger_level,
        stop_level=stop_level,
        invalidation_level=stop_level,
        d_projection=d_projection,
        non_entry_signal=non_entry_signal,
        signal_class=signal_class,
        trigger_mode=trigger_mode,
    )


def _build_intents(monkeypatch, setup: PatternResult, *, session: str = "RTH_MID"):
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("RUN_MODE_EFFECTIVE", "PAPER")
    return build_trade_intents(
        _STRATEGY_ID,
        "PR1030",
        _summary_with(setup),
        config=IntentPolicyConfig(min_confidence=0.6),
        trigger_ready_now=True,
        session=session,
    )


def test_pr1030_complete_setup_maps_to_entry_stop_target_and_rationale(monkeypatch) -> None:
    setup = _entry_setup()

    intents = _build_intents(monkeypatch, setup)

    assert len(intents) == 1
    intent = intents[0]
    assert intent.symbol == "PR1030"
    assert intent.direction == IntentDirection.LONG
    assert intent.entry_model == "Break of mapped trigger"
    assert intent.stop_model == "Below mapped structure low"
    assert intent.target_model == "Prior high / HOD extension"
    assert intent.time_in_force_policy == TimeInForcePolicy.DAY
    assert intent.rationale_text == setup.rationale_text
    assert intent.invalidations == []


def test_pr1030_missing_target_blocks_intent_creation(monkeypatch, capsys) -> None:
    setup = _entry_setup(target_suggestion=None)

    intents = _build_intents(monkeypatch, setup)

    assert intents == []
    output = capsys.readouterr().out
    assert "reason=missing_target" in output
    assert "outcome=CREATED" not in output


def test_pr1030_invalid_long_entry_stop_geometry_blocks_intent(monkeypatch, capsys) -> None:
    setup = _entry_setup(trigger_level=10.50, stop_level=10.55)

    intents = _build_intents(monkeypatch, setup)

    assert intents == []
    output = capsys.readouterr().out
    assert "reason=invalid_risk_geometry" in output
    assert "outcome=CREATED" not in output


def test_pr1030_abcd_projection_can_supply_target_model(monkeypatch) -> None:
    setup = _entry_setup(
        pattern_name="ABCD",
        setup_id="P_ABCD",
        setup_family_id="ABCD",
        trigger_level=10.80,
        stop_level=10.30,
        target_suggestion=None,
        d_projection=11.42,
    )

    intents = _build_intents(monkeypatch, setup, session="RTH_MID")

    assert len(intents) == 1
    assert intents[0].target_model == "ABCD measured move projection 11.4200"


def test_pr1030_risk_off_and_exit_signals_do_not_create_long_entry(monkeypatch, capsys) -> None:
    setup = _entry_setup(
        pattern_name="Parabolic Exhaustion",
        setup_id="P_PARABOLIC_EXHAUSTION",
        setup_family_id="PARABOLIC_EXHAUSTION",
        target_suggestion="Exit / reduce risk",
        non_entry_signal=True,
        signal_class="RISK_OFF",
        trigger_mode="EXIT_SIGNAL",
    )

    intents = _build_intents(monkeypatch, setup)

    assert intents == []
    output = capsys.readouterr().out
    assert "reason=risk_off_non_entry" in output
    assert "outcome=CREATED" not in output


def test_pr1030_pr6_positive_cases_have_exit_management_evidence() -> None:
    for case in build_pr6_positive_cases():
        result = run_ross_e2e_case(case)

        assert result.trade_intent_created is True
        assert result.risk_gate_called is True
        assert result.risk_approved is True
        assert result.execution_path == "SIMULATED_SAFE_NON_LIVE"
        assert result.execution_safe_non_live is True
        assert result.exit_evidence["status"] == "SIMULATED_MANAGEMENT_READY"
        assert result.exit_evidence["stop_model"]
        assert result.exit_evidence["target_model"]
        assert result.exit_evidence["exit_signal_capture"] == "available_without_live_order"
