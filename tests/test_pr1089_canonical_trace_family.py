from types import SimpleNamespace

import pytest

from src.setup_engine.setup_families.ross_families import ABCDPattern
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry, resolve_trace_setup_family
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.ross_momentum.tests.test_abcd_setup_family import _candles, _inputs
from test_pr1089_pullback_continuity_and_provenance import _provenance, _trace


@pytest.fixture(autouse=True)
def no_broker_calls(monkeypatch):
    from ibapi.client import EClient
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("Broker connections and orders are forbidden")
    for method in ("connect", "placeOrder", "cancelOrder"):
        monkeypatch.setattr(EClient, method, forbidden)
    yield
    assert calls == []


def test_real_registry_abcd_trace_and_rejection_family_are_canonical():
    inputs = _inputs(_candles([
        (10.2, 10.30, 10.10, 10.20, 1000),
        (10.1, 10.25, 9.90, 10.15, 1100),
        (10.2, 10.50, 10.15, 10.40, 1200),
        (10.5, 11.00, 10.40, 10.90, 1400),
        (10.8, 10.80, 10.50, 10.60, 900),
        (10.6, 10.70, 10.35, 10.45, 950),
        (10.5, 10.95, 10.45, 10.90, 1300),
        (10.9, 11.05, 10.90, 11.02, 1500),
    ]))
    registry = RossPatternRegistry()
    registry._patterns = [ABCDPattern()]
    traces = []
    results = registry.run(inputs, trace_context={"cycle_id": "cycle"}, trace_collector=traces.append)
    assert results[0].detected
    trace = traces[0]
    assert trace.pattern_id == "P_ABCD"
    assert trace.setup_family_id == trace.setup_family == "ABCD"
    provenance = RossMomentumStrategyV1._decision_rejection_provenance(
        {"rejected_candidates": [{"pattern_id": "P_ABCD", "setup_family": "ABCD"}]},
        SimpleNamespace(symbol=inputs.symbol, cycle_id="cycle", pattern_traces=traces),
    )
    assert provenance == {"selected_pattern_id": "P_ABCD", "selected_setup_family": "ABCD"}


@pytest.mark.parametrize("pattern,family,expected", [
    ("P_ABCD", "P_ABCD", "ABCD"),
    ("P_ABCD", "", "ABCD"),
    ("P_ABCD", "UNKNOWN", "ABCD"),
    ("P_THREE_BAR_PULLBACK", "P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK"),
    ("P_PARABOLIC_EXHAUSTION", "P_PARABOLIC_EXHAUSTION", "PARABOLIC_EXHAUSTION"),
    ("P_UNMAPPED", "P_UNMAPPED", None),
    ("P_UNMAPPED", "UNREGISTERED_FAMILY", None),
])
def test_canonical_family_boundary_uses_only_registry_authority(pattern, family, expected):
    assert resolve_trace_setup_family(pattern, family) == expected
    payload = _provenance(
        [_trace(pattern, family)], [{"pattern_id": pattern}],
        selected_setup_family=family, selected_pattern_id=pattern,
    )
    if expected is None:
        assert payload == {}
    else:
        assert payload == {"selected_setup_family": expected, "selected_pattern_id": pattern}


def test_canonical_family_prefers_authoritative_result_family():
    # GAP_CONTINUATION shares a registered pattern class with GAP_GO.
    assert resolve_trace_setup_family("P_GAP_GO", "GAP_CONTINUATION") == "GAP_CONTINUATION"
    assert resolve_trace_setup_family("P_GAP_GO", "GAP_GO") == "GAP_GO"


def test_canonical_family_multi_conflict_never_contains_pattern_ids():
    traces = [_trace("P_ABCD", "P_ABCD"), _trace("P_THREE_BAR_PULLBACK", "P_THREE_BAR_PULLBACK"),
              _trace("P_UNMAPPED", "P_UNMAPPED")]
    candidates = [{"pattern_id": t.pattern_id} for t in reversed(traces)]
    result = _provenance(traces, candidates, selected_setup_family="P_UNMAPPED", selected_pattern_id="P_UNMAPPED")
    assert result == {
        "selected_setup_families": ["ABCD", "THREE_BAR_PULLBACK"],
        "selected_pattern_ids": ["P_ABCD", "P_THREE_BAR_PULLBACK"],
    }
    assert all(not family.startswith("P_") for family in result["selected_setup_families"])


@pytest.mark.parametrize("trace_kwargs", [
    {"detected": False}, {"cycle_id": "old"}, {"symbol": "OTHER"}, None,
])
def test_canonical_family_resolution_cannot_bypass_detected_identity(trace_kwargs):
    traces = [] if trace_kwargs is None else [_trace("P_ABCD", "P_ABCD", **trace_kwargs)]
    assert _provenance(traces, [{"pattern_id": "P_ABCD"}],
                       selected_setup_family="P_ABCD", selected_pattern_id="P_ABCD") == {}


def test_known_legacy_gap_alias_retains_single_family_provenance():
    assert _provenance([_trace("P_GAP_GO", "P_GAP_GO")], [{"pattern_id": "P_GAP_GO"}]) == {
        "selected_setup_family": "GAP_GO", "selected_pattern_id": "P_GAP_GO",
    }
