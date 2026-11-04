"""Synthetic inputs; existing factory and actual Ross evaluation, no external I/O."""
from dataclasses import replace

import pytest

from src.setup_engine import registry as owner
from src.setup_engine.setup_families.ross_families import GapGoPattern
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_key_level_break_production_handoff import forbid_io
from test_ross_pr1029_pattern_detection_certification import _inputs, _levels

NAMES = ["GAP_GO", "GAP_CONTINUATION"]
ROWS = [(10.0,10.2,9.9,10.1,1000), (10.1,10.3,10.,10.2,1200),
        (10.2,10.4,10.1,10.3,1500), (10.3,10.6,10.2,10.5,3000)]


def inputs(symbol="ALIAS"):
    return _inputs(symbol=symbol, rows=ROWS, levels=_levels(prior_close=9.5),
                   news_context={"trend_up": "true", "impulse_active": "true", "macd": "0.2"})


def run(patterns, data):
    registry = RossPatternRegistry()
    registry._patterns = patterns
    traces = []
    results = registry.run(data, trace_collector=traces.append)
    return results, traces


@pytest.mark.parametrize("names", [NAMES, list(reversed(NAMES)), [NAMES[0]], [NAMES[1]]])
def test_enabled_names_evaluate_once_with_provenance(monkeypatch, names):
    patterns = owner.build_tradeable_patterns(names)
    assert len(patterns) == 1
    calls = []
    original = GapGoPattern.evaluate
    def count(self, data):
        calls.append(data)
        return original(self, data)
    monkeypatch.setattr(GapGoPattern, "evaluate", count)
    data = inputs()
    expected = original(patterns[0], data)
    results, traces = run(patterns, data)
    assert calls == [data]
    assert len(results) == len(traces) == 1
    result, trace = results[0], traces[0]
    assert result.detected == expected.detected is True
    assert result.trigger_type == expected.trigger_type
    assert result.trigger_level == expected.trigger_level
    assert result.stop_level == expected.stop_level
    assert result.target_suggestion == expected.target_suggestion
    assert result.rejection_reason == expected.rejection_reason
    assert result.setup_id == trace.pattern_id == "P_GAP_GO"
    assert trace.setup_family == "GAP_GO"
    assert result.setup_metadata["requested_setup_ids"] == trace.requested_setup_ids == sorted(names)


def test_each_context_is_evaluated_fresh(monkeypatch):
    patterns = owner.build_tradeable_patterns(NAMES)
    calls = []
    original = GapGoPattern.evaluate
    def count(self, data):
        calls.append(data)
        return original(self, data)
    monkeypatch.setattr(GapGoPattern, "evaluate", count)
    a = inputs(); b = inputs("OTHER")
    for data in (a, b, a, replace(a, candles=a.candles[:-1])):
        run(patterns, data)
    assert len(calls) == 4
    assert calls[0] is calls[2] is a


def test_rejection_and_error_are_single_and_keep_alias_trace(monkeypatch):
    patterns = owner.build_tradeable_patterns(NAMES)
    rejected, traces = run(patterns, replace(inputs(), candles=[]))
    assert len(rejected) == len(traces) == 1
    assert not rejected[0].detected
    assert traces[0].setup_family == "GAP_GO"
    assert rejected[0].setup_metadata["requested_setup_ids"] == sorted(NAMES)
    assert traces[0].requested_setup_ids == sorted(NAMES)
    calls = []
    def fail(self, data):
        calls.append(data)
        raise ValueError("synthetic")
    monkeypatch.setattr(GapGoPattern, "evaluate", fail)
    results, traces = run(patterns, inputs())
    assert len(calls) == len(traces) == 1
    assert results == []
    assert traces[0].final_outcome == "ERROR"
    assert traces[0].requested_setup_ids == sorted(NAMES)


def test_default_order_and_neighbor_enablement():
    patterns = owner.build_tradeable_patterns()
    assert len(patterns) == 27
    assert sum(isinstance(p, GapGoPattern) for p in patterns) == 1
    assert patterns[0].canonical_setup_id == "GAP_GO"
    assert patterns[1].canonical_setup_id == "ORB"
    assert [p.canonical_setup_id for p in owner.build_tradeable_patterns(["ORB", *reversed(NAMES)])] == ["GAP_GO", "ORB"]
    assert owner.build_tradeable_patterns([]) == []


def test_enablement_is_per_requested_entry(monkeypatch):
    canonical = owner.CANONICAL_SETUP_REGISTRY["GAP_GO"]
    monkeypatch.setitem(owner.CANONICAL_SETUP_REGISTRY, "GAP_GO", replace(canonical, status=owner.SetupImplementationStatus.DISABLED))
    patterns = owner.build_tradeable_patterns()
    gap = [p for p in patterns if isinstance(p, GapGoPattern)]
    assert len(gap) == 1
    assert gap[0].requested_setup_ids == ("GAP_CONTINUATION",)


def test_same_class_without_alias_is_not_collapsed(monkeypatch):
    monkeypatch.setitem(owner.CANONICAL_SETUP_REGISTRY, "DISTINCT", owner.SetupFamilyImplementation(
        "DISTINCT", GapGoPattern, owner.SetupImplementationStatus.TRADE_READY))
    patterns = owner.build_tradeable_patterns(["GAP_GO", "DISTINCT"])
    assert len(patterns) == 2
    assert patterns[0] is not patterns[1]


def test_invalid_alias_fails_closed(monkeypatch):
    spec = owner.CANONICAL_SETUP_REGISTRY["GAP_CONTINUATION"]
    monkeypatch.setitem(owner.CANONICAL_SETUP_REGISTRY, "GAP_CONTINUATION", replace(spec, canonical_setup_id="ORB"))
    with pytest.raises(ValueError, match="Invalid canonical detector alias"):
        owner.build_tradeable_patterns(NAMES)


def test_neighbor_contract_trace_and_trigger_keep_exact_occurrence():
    from src.core.engines.trigger_engine import TriggerEngine
    from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    from test_ross_selected_setup_handoff import consolidation_inputs
    data = consolidation_inputs()
    patterns = owner.build_tradeable_patterns(NAMES) + [ConsolidationBreakoutPattern()]
    results, traces = run(patterns, data)
    assert len(results) == len(traces) == 2
    assert results[1].detected
    assert results[1].setup_id == traces[1].pattern_id == "P_CONSOLIDATION_BREAK"
    bridge = RossMomentumStrategyV1._canonical_pattern_trigger_candidates(
        RossMomentumStrategyV1.__new__(RossMomentumStrategyV1), results,
        symbol=data.symbol, existing_triggers=[])
    assert len(bridge) == 1  # Existing GAP_GO bridge gap is not repaired here.
    selected = RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="CONSOLIDATION_BREAKOUT", trigger_candidates=bridge,
        selected_candidate_index=1)
    assert selected is bridge[0]
    assert selected["canonical_result_index"] == 1
    assert selected["trigger_level"] == results[1].trigger_level
    assert selected["stop_level"] == results[1].stop_level
    assert selected["setup_metadata"] == results[1].setup_metadata
    evaluated = TriggerEngine().evaluate_triggers(
        symbol=data.symbol, candles=data.candles, setups=[selected], levels={}, structure={})
    assert evaluated[0]["trigger_ready_now"] is True
    assert evaluated[0]["setup_family_id"] == "CONSOLIDATION_BREAKOUT"
