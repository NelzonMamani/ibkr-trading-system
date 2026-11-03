"""Synthetic market streams; actual detector, registry, V1 and registered trigger."""
from dataclasses import replace
from datetime import timedelta

import pytest

from src.config.runtime_config import RunMode
from src.core.engines.trigger_engine import TriggerEngine
from src.setup_engine.setup_families.ross_families import KeyLevelBreakPattern
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from test_key_level_break_pattern import _base_inputs
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _snapshot, _watchlist_row, _reset_config, FakeRegistry,
)


@pytest.fixture(autouse=True)
def forbid_io(monkeypatch):
    import socket
    from ibapi.client import EClient
    def forbidden(*args, **kwargs):
        pytest.fail("network/broker/mutation forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for name in ("connect", "reqHistoricalData", "reqMktData", "placeOrder", "cancelOrder"):
        monkeypatch.setattr(EClient, name, forbidden)


def _result():
    result = KeyLevelBreakPattern().evaluate(_base_inputs())
    assert result.detected and result.target_suggestion
    return result


def _bridge(results):
    return RossMomentumStrategyV1._canonical_pattern_trigger_candidates(
        RossMomentumStrategyV1.__new__(RossMomentumStrategyV1), results,
        symbol="KLB", existing_triggers=[])


def test_real_contract_reaches_registered_evaluator(monkeypatch):
    result = _result()
    setups = _bridge([result])
    assert len(setups) == 1
    setup = setups[0]
    assert setup["canonical_result_index"] == 0
    assert setup["setup_metadata"] == result.setup_metadata
    assert setup["trigger_level"] == result.trigger_level
    assert setup["stop_level"] == result.stop_level
    assert setup["invalidation_level"] == result.invalidation_level
    seen = []
    original = TRIGGER_EVALUATOR_REGISTRY["KEY_LEVEL_BREAK"]
    def observed(payload, inputs):
        seen.append((payload, inputs))
        return original(payload, inputs)
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY, "KEY_LEVEL_BREAK", observed)
    trigger = TriggerEngine().evaluate_triggers(
        symbol="KLB", candles=_base_inputs().candles, setups=setups, levels={}, structure={})[0]
    assert len(seen) == 1 and seen[0][0] is setup
    assert seen[0][1]["candles"] == _base_inputs().candles
    assert trigger["trigger_reason"] == "key_level_break_confirmed"
    assert trigger["trigger_ready_now"]
    assert trigger["canonical_result_index"] == 0
    assert trigger["invalidation_price_reference"] == result.invalidation_level
    assert trigger["stop_price_reference"] == result.stop_level


def _run(monkeypatch, tmp_path, *, state="ready", results=None):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    primary_rows = [(9.8, 9.95, 9.75, 9.9, 900)] * 49 + [(9.9, 10.08, 9.88, 10.03, 1200)]
    execution_rows = list(primary_rows)
    if state == "not_ready":
        execution_rows[-1] = (9.9, 10.08, 9.88, 10.03, 800)
    elif state == "invalidated":
        execution_rows[-1] = (9.9, 10.08, 9.88, 9.99, 1200)
    data = {tf: _candles(execution_rows if tf == "10s" else primary_rows,
                        step_seconds=step) for tf, step in (("1m", 60), ("5m", 300), ("10s", 10))}
    if state == "missing":
        data["10s"] = []
    elif state == "stale":
        data["10s"] = [replace(c, timestamp=c.timestamp-timedelta(minutes=10)) for c in data["10s"]]
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
                        lambda *, timeframe="1m", **kwargs: data[timeframe])
    captured = []
    if results is None:
        registry = RossPatternRegistry()
        registry._patterns = [KeyLevelBreakPattern()]
        original_run = registry.run
        def run(*args, **kwargs):
            output = original_run(*args, **kwargs)
            captured.extend(output)
            return output
        monkeypatch.setattr(registry, "run", run)
        strategy._pattern_registry = registry
    else:
        strategy._pattern_registry = FakeRegistry(results)
        captured = results
    row = {**_watchlist_row(), "premarket_high": 10.0, "last_price": 10.03,
           "bid": 10.02, "ask": 10.04}
    snapshot = replace(_snapshot(), bid=10.02, ask=10.04, last=10.03)
    intents = strategy.process_watchlist(
        watchlist=[row], snapshots={"UPC": snapshot}, session_label="RTH_OPEN",
        session_phase="RTH_OPEN", timestamp_utc="synthetic-klb", mode=RunMode.READ_ONLY)
    return strategy, intents, captured


@pytest.mark.parametrize("state", ["ready", "not_ready", "invalidated", "missing", "stale"])
def test_real_detector_through_actual_v1(monkeypatch, tmp_path, state):
    seen = []
    evaluator = TRIGGER_EVALUATOR_REGISTRY["KEY_LEVEL_BREAK"]
    def observed(payload, inputs):
        seen.append((payload, inputs))
        return evaluator(payload, inputs)
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY, "KEY_LEVEL_BREAK", observed)
    strategy, intents, results = _run(monkeypatch, tmp_path, state=state)
    assert results and results[0].detected
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    if state == "ready":
        assert len(intents) == 1, terminal
        result = results[0]
        intent = intents[0]
        assert intent.setup_family_id == "KEY_LEVEL_BREAK"
        assert intent.entry_price == result.trigger_level
        assert intent.stop_loss_price == result.stop_level
        assert intent.target_model == result.target_suggestion
        assert result.rationale_text in intent.rationale
        assert intent.take_profit_price is None
        assert intent.timestamp_utc == "synthetic-klb"
        assert len(seen) == 1
        assert seen[0][0]["setup_metadata"] == result.setup_metadata
        observed_candles = seen[0][1]["candles"]
        assert observed_candles[-1].timestamp - observed_candles[-2].timestamp == timedelta(seconds=10)
        assert all(c.timestamp.tzinfo is not None for c in observed_candles)
        assert (observed_candles[-1].open, observed_candles[-1].close,
                observed_candles[-1].volume) == (9.9, 10.03, 1200)
        own = next(t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
                   if t.get("setup_family_id") == "KEY_LEVEL_BREAK")
        assert own["execution_stream"]["execution_trigger_timeframe"] == "10s"
        assert own["execution_stream"]["timeframe_substitution"] is False
    else:
        assert intents == []
        assert not terminal["intent_emitted"]
        triggers = strategy._failure_trace_collector._symbols[-1].input_summary.get("trigger_candidates", [])
        own = [t for t in triggers if t.get("setup_family_id") == "KEY_LEVEL_BREAK"]
        assert len(own) == 1 and not own[0]["trigger_ready_now"]
        expected = {"not_ready": "awaiting_decisive_break_and_acceptance",
                    "invalidated": "at_or_below_invalidation", "missing": "execution_stream_missing",
                    "stale": "execution_stream_stale"}
        assert own[0]["trigger_reason"] == expected[state]


@pytest.mark.parametrize("reverse", [False, True])
def test_same_id_rejected_contract_cannot_replace_winner(monkeypatch, tmp_path, reverse):
    valid = _result()
    invalid = replace(valid, target_suggestion=None, trigger_level=99., stop_level=90.,
                      rationale_text="Rejected occurrence must never be borrowed")
    results = [invalid, valid] if reverse else [valid, invalid]
    strategy, intents, _ = _run(monkeypatch, tmp_path, results=results)
    assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert intents[0].entry_price == valid.trigger_level
    assert intents[0].stop_loss_price == valid.stop_level
    assert intents[0].target_model == valid.target_suggestion
    assert invalid.rationale_text not in intents[0].rationale


@pytest.mark.parametrize("field,value", [("target_suggestion", None), ("rationale_text", ""),
                                         ("stop_level", None)])
def test_invalid_contract_cannot_form_intent(monkeypatch, tmp_path, field, value):
    result = replace(_result(), **{field: value})
    strategy, intents, _ = _run(monkeypatch, tmp_path, results=[result])
    assert intents == []
    assert strategy.last_symbol_terminal_outcomes["UPC"]["reason"] == "all_detected_candidates_rejected"


@pytest.mark.parametrize("reverse", [False, True])
def test_selected_same_id_cannot_borrow_lower_ranked_ready_trigger(monkeypatch, tmp_path, reverse):
    valid = _result()
    waiting = replace(valid, confidence=.99, trigger_level=10.04,
                      setup_metadata={**valid.setup_metadata, "occurrence": "selected_waiting"})
    results = [waiting, valid] if reverse else [valid, waiting]
    strategy, intents, _ = _run(monkeypatch, tmp_path, results=results)
    assert intents == []
    triggers = [t for t in strategy._failure_trace_collector._symbols[-1].input_summary["trigger_candidates"]
                if t.get("setup_family_id") == "KEY_LEVEL_BREAK"]
    selected_index = results.index(waiting)
    selected = next(t for t in triggers if t["canonical_result_index"] == selected_index)
    other = next(t for t in triggers if t["canonical_result_index"] != selected_index)
    assert not selected["trigger_ready_now"] and other["trigger_ready_now"]
    assert selected["trigger_price_reference"] == waiting.trigger_level
    assert not strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]
