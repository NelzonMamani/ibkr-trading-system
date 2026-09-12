from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.setup_engine.setup_families.pullbacks import SecondPullbackPattern, ThreeBarPullbackPattern
from src.strategies.common.triggers.trigger_pullback_variants import (
    evaluate_second_pullback_trigger, evaluate_three_bar_pullback_trigger,
)
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _execution_bars, _inputs, _rows, _snapshot, _trigger_payload, _watchlist_row,
)


@pytest.fixture(autouse=True)
def _read_only_config(monkeypatch):
    monkeypatch.delenv("FORCE_SESSION", raising=False)
    set_config_overrides({
        "RUN_MODE": "READ_ONLY", "RUN_MODE_EFFECTIVE": "READ_ONLY",
        "EXECUTION_ENABLED": False, "IBKR_FALLBACK_ENABLED": False,
        "ROSS_MOMENTUM_STRATEGY_ENABLED": True, "SELECTED_STRATEGY": "ross_momentum",
        "ROSS_VALIDATION_OVERRIDE_ENABLED": False, "MANUAL_FOCUS_ENABLED": False,
    })
    yield
    set_config_overrides(None)


def _case(family):
    if family == "THREE_BAR_PULLBACK":
        rows = _rows("not_ready")
        wait = (10.30, 10.40, 10.20, 10.32, 900)
        fire = (10.32, 10.50, 10.20, 10.48, 1600)
        invalid = (10.32, 10.40, 10.07, 10.30, 900)
        return ThreeBarPullbackPattern(), evaluate_three_bar_pullback_trigger, rows, wait, fire, invalid
    rows = _rows("second_ready")[:-1] + [(10.45, 10.58, 10.44, 10.50, 1000)]
    wait = (10.50, 10.58, 10.44, 10.52, 1000)
    fire = (10.52, 10.65, 10.44, 10.62, 1600)
    invalid = (10.52, 10.58, 10.39, 10.50, 1000)
    return SecondPullbackPattern(), evaluate_second_pullback_trigger, rows, wait, fire, invalid


def _history_inputs(rows):
    inputs = _inputs()
    candles = _candles(rows)
    return replace(inputs, execution_refinement_timeframe=inputs.primary_timeframe, candles=candles, timeframe_candles={**inputs.timeframe_candles, inputs.primary_timeframe: candles})


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
@pytest.mark.parametrize("extra_waits", [0, 3])
def test_armed_pullback_delayed_trigger(family, extra_waits):
    pattern, evaluate_trigger, rows, wait, fire, _ = _case(family)
    original = pattern.evaluate(_history_inputs(rows))
    assert original.detected
    for count in range(extra_waits + 1):
        inputs = _history_inputs(rows + [wait] * count)
        result = pattern.evaluate(inputs)
        trigger = evaluate_trigger(_trigger_payload(result), {"candles": inputs.candles})
        assert result.detected
        assert trigger["trigger_state"] == "ARMED"
        assert "ARMED_WAITING" in trigger["quality_flags"]
        assert (result.trigger_level, result.stop_level, result.invalidation_level) == (
            original.trigger_level, original.stop_level, original.invalidation_level,
        )
    inputs = _history_inputs(rows + [wait] * extra_waits + [fire])
    result = pattern.evaluate(inputs)
    trigger = evaluate_trigger(_trigger_payload(result), {"candles": inputs.candles})
    assert result.detected
    assert result.setup_family_id == family
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_state"] == "FIRED"
    assert result.setup_metadata["origin_timestamp"] == inputs.candles[45].timestamp
    assert result.setup_metadata["structure_completed_timestamp"] == inputs.candles[48].timestamp
    assert result.setup_metadata["timeframe_provenance"] == inputs.timeframe_provenance
    assert trigger["trigger_price_reference"] == original.trigger_level
    assert trigger["invalidation_price_reference"] == original.invalidation_level


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_armed_pullback_invalidation_cannot_recover(family):
    pattern, _, rows, wait, fire, invalid = _case(family)
    for tail in ([invalid], [invalid, wait, fire]):
        result = pattern.evaluate(_history_inputs(rows + tail))
        assert result.detected is False
        assert result.rejection_reason == "structural_invalidation_breached"


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_armed_pullback_consumed_breakout_cannot_refire(family):
    pattern, _, rows, wait, fire, _ = _case(family)
    result = pattern.evaluate(_history_inputs(rows + [fire, wait, fire]))
    assert result.detected is False
    assert result.rejection_reason == "pullback_breakout_already_consumed"


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_armed_pullback_uses_current_volume_contract(family):
    pattern, evaluate_trigger, rows, _, fire, _ = _case(family)
    weak_fire = (*fire[:4], 1)
    inputs = _history_inputs(rows + [weak_fire])
    result = pattern.evaluate(inputs)
    assert result.detected
    trigger = evaluate_trigger(_trigger_payload(result), {"candles": inputs.candles})
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_reason"] == "breakout_volume_confirmation_failed"


def test_armed_pullback_families_remain_distinct():
    three, _, three_rows, _, _, _ = _case("THREE_BAR_PULLBACK")
    second, _, second_rows, _, _, _ = _case("SECOND_PULLBACK")
    assert three.evaluate(_history_inputs(three_rows)).detected
    assert not second.evaluate(_history_inputs(three_rows)).detected
    assert second.evaluate(_history_inputs(second_rows)).detected
    assert not three.evaluate(_history_inputs(second_rows)).detected


def test_armed_pullback_newest_origin_supersedes_old_consumed_structure():
    pattern, _, rows, _, fire, _ = _case("THREE_BAR_PULLBACK")
    # A later complete origin has different authoritative levels.
    newer = [(o + 1, h + 1, l + 1, c + 1, v) for o, h, l, c, v in rows[-5:]]
    inputs = _history_inputs(rows + [fire] + newer)
    result = pattern.evaluate(inputs)
    assert result.detected
    assert result.trigger_level == pytest.approx(11.44)
    assert result.setup_metadata["origin_timestamp"] == inputs.candles[-5].timestamp


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
@pytest.mark.parametrize("invalidated", [False, True])
def test_armed_pullback_real_strategy_delayed_outcome(monkeypatch, tmp_path, family, invalidated):
    from ibapi.client import EClient
    calls = []
    def forbid_order(*args, **kwargs):
        calls.append(1)
        raise AssertionError("broker mutation forbidden")
    monkeypatch.setattr(EClient, "placeOrder", forbid_order)
    monkeypatch.setattr(EClient, "cancelOrder", forbid_order)
    pattern, _, rows, wait, fire, invalid = _case(family)
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    registry = RossPatternRegistry()
    registry._patterns = [pattern]
    strategy._pattern_registry = registry
    history = list(rows)
    def bars(*, timeframe="1m", limit=50, **kwargs):
        if timeframe == "10s":
            return _execution_bars(_candles(history))[-limit:]
        return _candles(history, step_seconds={"1m": 60, "5m": 300}[timeframe])[-limit:]
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars", bars)
    def run(cycle):
        row = _watchlist_row()
        row.update(last_price=history[-1][3], bid=history[-1][3] - .01, ask=history[-1][3] + .01)
        snapshot = replace(_snapshot(), last=history[-1][3], bid=history[-1][3] - .01, ask=history[-1][3] + .01)
        return strategy.process_watchlist(
            watchlist=[row], snapshots={"UPC": snapshot}, session_label="RTH",
            timestamp_utc=cycle, mode=RunMode.READ_ONLY, session_phase="RTH_OPEN",
        )
    assert run("armed-cycle") == []
    assert strategy.last_symbol_terminal_outcomes["UPC"]["trigger_ready_now"] is False
    history.append(invalid if invalidated else wait)
    assert run("waiting-cycle") == []
    history.append(fire)
    intents = run("later-cycle")
    if invalidated:
        assert intents == []
    else:
        assert len(intents) == 1
        assert intents[0].setup_family_id == family
        assert intents[0].trigger_ready
        assert not getattr(intents[0], "synthetic_forced_intent", False)
    assert calls == []


def _trace(pattern, family, *, detected=True, symbol="UPC", cycle_id="cycle"):
    return SimpleNamespace(pattern_id=pattern, setup_family_id=family, detected=detected, symbol=symbol, cycle_id=cycle_id)


def _provenance(traces, candidates, **decision):
    return RossMomentumStrategyV1._decision_rejection_provenance(
        {"rejected_candidates": candidates, **decision},
        SimpleNamespace(symbol="UPC", cycle_id="cycle", pattern_traces=traces),
    )


def test_rejection_provenance_only_detected_candidate_among_registry_rejections():
    traces = [_trace("P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK")]
    traces += [_trace("P_" + family, family, detected=False) for family in ["SECOND_PULLBACK", "BULL_FLAG", "ABCD", "PARABOLIC_EXHAUSTION"]]
    candidates = [{"pattern_id": t.pattern_id, "setup_family": t.setup_family_id} for t in traces]
    assert _provenance(traces, candidates) == {
        "selected_setup_family": "THREE_BAR_PULLBACK", "selected_pattern_id": "P_THREE_BAR_PULLBACK",
    }


@pytest.mark.parametrize("trace_kwargs", [
    {"detected": False}, {"symbol": "OTHER"}, {"cycle_id": "old-cycle"},
    {"symbol": ""}, {"cycle_id": ""}, None,
])
def test_rejection_provenance_requires_matching_detected_trace(trace_kwargs):
    traces = [] if trace_kwargs is None else [_trace("P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK", **trace_kwargs)]
    assert _provenance(
        traces, [{"pattern_id": "P_THREE_BAR_PULLBACK", "setup_family": "THREE_BAR_PULLBACK"}],
        selected_setup_family="THREE_BAR_PULLBACK", selected_pattern_id="P_THREE_BAR_PULLBACK",
    ) == {}


def test_rejection_provenance_detected_conflict_excludes_undetected():
    traces = [
        _trace("P_SECOND_PULLBACK", "SECOND_PULLBACK"),
        _trace("P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK"),
        _trace("P_ABCD", "ABCD", detected=False),
    ]
    candidates = [{"pattern_id": t.pattern_id, "setup_family": t.setup_family_id} for t in traces]
    assert _provenance(traces, candidates[::-1]) == {
        "selected_setup_families": ["SECOND_PULLBACK", "THREE_BAR_PULLBACK"],
        "selected_pattern_ids": ["P_SECOND_PULLBACK", "P_THREE_BAR_PULLBACK"],
    }


def test_rejection_provenance_does_not_trust_candidate_family():
    trace = _trace("P_PARABOLIC_EXHAUSTION", "PARABOLIC_EXHAUSTION")
    assert _provenance([trace], [{"pattern_id": trace.pattern_id, "setup_family": "ABCD"}]) == {
        "selected_setup_family": "PARABOLIC_EXHAUSTION", "selected_pattern_id": "P_PARABOLIC_EXHAUSTION",
    }


@pytest.mark.parametrize("candidate_flags", [{"detected": False}, {"reason": "not_detected"}])
def test_rejection_provenance_non_detected_candidate_cannot_contribute(candidate_flags):
    trace = _trace("P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK")
    assert _provenance([trace], [{"pattern_id": trace.pattern_id, **candidate_flags}]) == {}


def test_rejection_provenance_fallback_requires_detected_identity():
    assert _provenance([_trace("P_ABCD", "ABCD", detected=False)], []) == {}
    assert _provenance([_trace("P_ABCD", "ABCD", cycle_id="old-cycle")], []) == {}
    assert _provenance([_trace("P_PARABOLIC_EXHAUSTION", "PARABOLIC_EXHAUSTION")], []) == {
        "selected_setup_family": "PARABOLIC_EXHAUSTION", "selected_pattern_id": "P_PARABOLIC_EXHAUSTION",
    }

def test_rejection_provenance_from_real_decision_engine_excludes_registry_misses():
    from src.core.engines.decision_engine import DecisionEngine
    from test_pr1082_trigger_to_intent_terminal_semantics import _detected_parabolic_exhaustion, _detected_pullback

    results = [
        _detected_parabolic_exhaustion(),
        replace(_detected_pullback("P_THREE_BAR_PULLBACK"), detected=False),
        replace(_detected_pullback("P_SECOND_PULLBACK"), detected=False),
    ]
    traces = [_trace(r.setup_id, r.setup_family_id, detected=r.detected) for r in results]
    decision = DecisionEngine().compute_decision(
        symbol="UPC", levels={}, structure={}, setups=[], pattern_results=results,
        pattern_traces=traces, session_context="RTH",
    )
    assert len(decision["rejected_candidates"]) == 3
    assert _provenance(traces, decision["rejected_candidates"]) == {
        "selected_setup_family": "PARABOLIC_EXHAUSTION",
        "selected_pattern_id": "P_PARABOLIC_EXHAUSTION",
    }


def test_armed_pullback_newer_invalidated_origin_does_not_revive_older():
    pattern, _, rows, _, _, _ = _case("THREE_BAR_PULLBACK")
    newer = [(o + 1, h + 1, l + 1, c + 1, v) for o, h, l, c, v in rows[-5:]]
    newer[-1] = (11.12, 11.36, 11.07, 11.32, 1000)
    result = pattern.evaluate(_history_inputs(rows + newer))
    assert not result.detected
    assert result.rejection_reason == "structural_invalidation_breached"
