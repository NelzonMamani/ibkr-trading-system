"""Synthetic market data; real Flat Top detector/registry/dispatch/selection/V1.

Only the market-data boundary supplies fixtures. Observers call the original
owners and never manufacture or complete a PatternResult or trigger contract.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from src.config.runtime_config import RunMode
from src.setup_engine.registry import build_tradeable_patterns
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_key_level_break_production_handoff import forbid_io
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _snapshot, _watchlist_row, _reset_config,
)


TAIL = [
    (10.02, 10.18, 9.99, 10.14, 1000),
    (10.14, 10.19, 10.05, 10.16, 1050),
    (10.16, 10.20, 10.08, 10.17, 1020),
    (10.17, 10.19, 10.10, 10.18, 1100),
    (10.18, 10.30, 10.14, 10.27, 1600),
]


@pytest.fixture(autouse=True)
def forbid_collection_and_execution(monkeypatch, forbid_io):
    from ibapi.client import EClient
    from src.execution.execution_engine import ExecutionEngine
    import urllib.request
    import socket
    import sys
    def forbidden(*args, **kwargs):
        pytest.fail("collection, broker inquiry and execution forbidden")
    for name in ("reqPositions", "reqAllOpenOrders", "reqOpenOrders", "reqExecutions",
                 "reqContractDetails", "reqGlobalCancel"):
        monkeypatch.setattr(EClient, name, forbidden)
    monkeypatch.setattr(ExecutionEngine, "execute_trade", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    # Do not turn an optional HTTP package into a new offline-test dependency.
    if sessions := sys.modules.get("requests.sessions"):
        monkeypatch.setattr(sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "sendto", forbidden)


def actual_run(monkeypatch, tmp_path, *, state="ready", duplicate=False):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    rows = [(10.0, 10.12, 9.98, 10.08, 900)] * 45 + TAIL
    execution = list(rows)
    if state == "failed_breakout":
        rows[-1] = (10.18, 10.30, 10.14, 10.20, 1600)
    if state == "weak_volume":
        rows[-1] = (10.18, 10.30, 10.14, 10.27, 600)
    if state == "nonflat":
        rows[-3] = (10.16, 10.40, 10.08, 10.17, 1020)
    if state == "waiting":
        execution[-1] = (10.15, 10.19, 10.14, 10.18, 1600)
    if state == "execution_touch":
        execution[-1] = (10.15, 10.20, 10.14, 10.20, 1600)
    if state in {"source_at_threshold", "source_below_threshold"}:
        close = 10.2 + max(.02, 10.2*.003)*.25
        rows[-1] = (10.18, 10.30, 10.14,
                    close-(1e-9 if state == "source_below_threshold" else 0), 1600)
    data = {tf: _candles(execution if tf == "10s" else rows,
                        end=datetime(2026, 9, 16, 14, 30 if tf == "5m" else (35 if tf == "10s" else 34),
                                     20 if tf == "10s" else 0, tzinfo=timezone.utc),
                        step_seconds=step)
            for tf, step in (("1m", 60), ("5m", 300), ("10s", 10))}
    for prefix, tf in (("source", "1m"), ("execution", "10s")):
        if state == prefix + "_missing":
            data[tf] = []
        elif state == prefix + "_stale":
            data[tf] = [replace(c, timestamp=c.timestamp-timedelta(minutes=10)) for c in data[tf]]
        elif state == prefix + "_future":
            data[tf][-1] = replace(data[tf][-1], timestamp=datetime(2026, 9, 16, 14, 35, 30, 1, tzinfo=timezone.utc))
        elif state == prefix + "_nan_low":
            data[tf][-1] = replace(data[tf][-1], low=float("nan"))
        elif state == prefix + "_malformed":
            data[tf][-1] = replace(data[tf][-1], low=11.)
    if state == "source_forming":
        data["1m"][-1] = replace(data["1m"][-1], timestamp=datetime(2026, 9, 16, 14, 35, tzinfo=timezone.utc))
    if state in {"exact_completion", "before_completion"}:
        data["1m"][-1] = replace(data["1m"][-1], timestamp=datetime(
            2026, 9, 16, 14, 34, 30, 1 if state == "before_completion" else 0, tzinfo=timezone.utc))
    if state == "forming_tail":
        data["1m"].append(replace(data["1m"][-1], open=10.27, high=99., low=1.,
                                timestamp=datetime(2026, 9, 16, 14, 35, tzinfo=timezone.utc)))
    if state == "confirm_extremes":
        data["1m"][-1] = replace(data["1m"][-1], high=99., low=1.)
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
                        lambda *, timeframe="1m", limit=50, **kw: list(data[timeframe])[-limit:])
    registry = RossPatternRegistry()
    registry._patterns = build_tradeable_patterns(["FLAT_TOP_BREAKOUT"])
    if duplicate:
        registry._patterns.extend(build_tradeable_patterns(["FLAT_TOP_BREAKOUT"]))
    strategy._pattern_registry = registry
    results, calls, seen_inputs = [], [], []
    original_run = registry.run
    def observed_run(inputs, **kwargs):
        seen_inputs.append(inputs)
        output = original_run(inputs, **kwargs)
        results.extend(output)
        return output
    monkeypatch.setattr(registry, "run", observed_run)
    original = TRIGGER_EVALUATOR_REGISTRY["FLAT_TOP_BREAKOUT"]
    def observed(payload, inputs):
        output = original(payload, inputs)
        calls.append((payload, inputs, output))
        return output
    monkeypatch.setitem(TRIGGER_EVALUATOR_REGISTRY, "FLAT_TOP_BREAKOUT", observed)
    row = {**_watchlist_row(), "last_price": 10.27, "bid": 10.26, "ask": 10.28}
    snapshot = replace(_snapshot(), last=10.27, bid=10.26, ask=10.28)
    intents = strategy.process_watchlist(
        watchlist=[row], snapshots={"UPC": snapshot}, session_label="RTH_OPEN",
        session_phase="RTH_OPEN", timestamp_utc="synthetic-flat-top", mode=RunMode.READ_ONLY)
    return strategy, intents, results, calls, seen_inputs


def test_unmodified_detector_through_actual_v1(monkeypatch, tmp_path):
    strategy, intents, results, calls, seen = actual_run(monkeypatch, tmp_path)
    assert len(results) == 1 and results[0].detected
    result = results[0]
    assert result.trigger_level == 10.20
    assert result.stop_level == result.invalidation_level == 9.99
    assert seen[0].levels.hod == 10.30  # Context HOD is not the selected resistance.
    canonical = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
    assert len(canonical) == len(intents) == 1, strategy.last_symbol_terminal_outcomes
    assert canonical[0][0]["canonical_result_index"] == 0
    assert canonical[0][2]["trigger_ready_now"]
    intent = intents[0]
    assert intent.entry_price == result.trigger_level
    assert intent.stop_loss_price == result.stop_level
    assert intent.invalidation_level == result.invalidation_level
    assert intent.target_model == result.target_suggestion
    assert intent.take_profit_price is None
    assert result.rationale_text in intent.rationale
    assert intent.timestamp_utc == "synthetic-flat-top"
    assert intent.setup_family_id == "FLAT_TOP_BREAKOUT"
    assert intent.setup_metadata["canonical_result_index"] == 0
    assert intent.setup_metadata["execution_stream"]["observed_at_utc"] == seen[0].observed_at_utc.isoformat()


@pytest.mark.parametrize("state", [
    "waiting", "failed_breakout", "weak_volume", "nonflat",
    "source_missing", "source_stale", "execution_missing", "execution_stale",
    "source_future", "execution_future", "source_nan_low", "execution_nan_low",
    "source_malformed", "execution_malformed", "source_forming",
    "source_below_threshold",
])
def test_negative_market_inputs_do_not_form_intents(monkeypatch, tmp_path, state):
    _, intents, results, calls, _ = actual_run(monkeypatch, tmp_path, state=state)
    assert intents == []
    if state in {"source_future", "source_nan_low", "source_malformed"}:
        assert len(results) == 1 and not results[0].detected
        assert results[0].rejection_reason == (
            "FUTURE_CANDLE_DATA" if state == "source_future" else "INVALID_CANDLE_DATA")
    if state in {"execution_future", "execution_nan_low", "execution_malformed"}:
        assert results[0].detected
        canonical = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
        assert len(canonical) == 1
        assert canonical[0][2]["trigger_reason"] == (
            "flat_top_future_candle_data" if state == "execution_future" else "flat_top_invalid_candle_data")


@pytest.mark.parametrize("state", ["exact_completion", "forming_tail", "confirm_extremes",
                                   "execution_touch", "source_at_threshold"])
def test_only_completed_structural_window_supplies_anchors(monkeypatch, tmp_path, state):
    _, intents, results, _, _ = actual_run(monkeypatch, tmp_path, state=state)
    assert len(intents) == 1
    assert results[0].trigger_level == intents[0].entry_price == 10.20
    assert results[0].stop_level == results[0].invalidation_level == 9.99
    assert intents[0].stop_loss_price == intents[0].invalidation_level == 9.99


def test_one_microsecond_before_completion_is_not_a_confirmed_source_breakout(monkeypatch, tmp_path):
    _, intents, results, _, _ = actual_run(monkeypatch, tmp_path, state="before_completion")
    assert intents == []
    assert results and not results[0].detected


def test_serialized_raw_evidence_is_isolated_from_later_mutation(monkeypatch, tmp_path):
    _, intents, results, calls, inputs = actual_run(monkeypatch, tmp_path)
    intent = intents[0]
    saved = asdict(intent)
    canonical = next(p for p, _, _ in calls if p.get("source") == "canonical_pattern_result")
    canonical["execution_stream"]["timeframe_provenance"].clear()
    canonical["setup_metadata"]["mutated"] = True
    results[0].setup_metadata["later"] = True
    inputs[0].candles.clear()
    assert asdict(intent) == saved


def test_real_duplicate_occurrences_keep_ordinal_identity(monkeypatch, tmp_path):
    # No prepared result: configure two native instances and keep registry/detector
    # behavior. Repeated calls are independent, not a persistent deduplication cache.
    strategy, intents, results, calls, _ = actual_run(monkeypatch, tmp_path, duplicate=True)
    assert len(results) == 2 and results[0] is not results[1]
    assert all(result.detected for result in results)
    canonical = [c for c in calls if c[0].get("source") == "canonical_pattern_result"]
    assert [c[0]["canonical_result_index"] for c in canonical] == [0, 1]
    assert len(intents) == 1
    selected = intents[0].setup_metadata["canonical_result_index"]
    assert selected == 0  # Stable tie ranking keeps the first occurrence.
    own = canonical[selected][0]
    assert own["canonical_result_index"] == selected
    assert own["trigger_level"] == intents[0].entry_price
    assert own["stop_level"] == intents[0].stop_loss_price
    results[1].setup_metadata["unselected_mutation"] = True
    assert "unselected_mutation" not in intents[0].setup_metadata


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_native_contracts_cannot_borrow_a_ready_occurrence(monkeypatch, tmp_path, reverse):
    """Adversarial selector boundary using two real detector outputs, not V1 injection."""
    from copy import deepcopy
    from src.core.engines.trigger_engine import TriggerEngine
    from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern
    strategy, _, results, calls, inputs = actual_run(monkeypatch, tmp_path)
    shifted = replace(inputs[0], candles=[replace(c, open=c.open+1, high=c.high+1,
        low=c.low+1, close=c.close+1) for c in inputs[0].candles])
    second = FlatTopBreakoutPattern().evaluate(shifted)
    assert second.detected and second.trigger_level == pytest.approx(11.2)
    native = [second, results[0]] if reverse else [results[0], second]
    setups = strategy._canonical_pattern_trigger_candidates(native, symbol="UPC", existing_triggers=[])
    stream = next(p["execution_stream"] for p, _, _ in calls if p.get("source") == "canonical_pattern_result")
    for setup in setups:
        setup["execution_stream"] = deepcopy(stream)
    triggers = TriggerEngine().evaluate_triggers(symbol="UPC", setups=setups,
        candles=inputs[0].timeframe_candles["10s"], levels={}, structure={})
    waiting_index = 0 if reverse else 1
    ready_index = 1-waiting_index
    waiting = strategy._select_trigger_candidate(setup_family_id="FLAT_TOP_BREAKOUT",
        trigger_candidates=triggers, selected_candidate_index=waiting_index)
    ready = strategy._select_trigger_candidate(setup_family_id="FLAT_TOP_BREAKOUT",
        trigger_candidates=triggers, selected_candidate_index=ready_index)
    assert not waiting["trigger_ready_now"] and ready["trigger_ready_now"]
    assert waiting["trigger_price_reference"] == second.trigger_level
    assert strategy._select_trigger_candidate(setup_family_id="FLAT_TOP_BREAKOUT",
        trigger_candidates=triggers) is None  # Ambiguous duplicate ID never guesses.
    reasons = []
    assert strategy._build_trade_from_pattern(second, inputs[0], selected_trigger=ready,
        selected_contract=second, rejection_reasons=reasons) is None
    assert reasons == ["selected_invalidation_authority_mismatch"]


@pytest.mark.parametrize("field", ["spread", "rvol"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_liquidity_cannot_qualify_a_real_detector(monkeypatch, tmp_path, field, bad):
    from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern
    _, _, _, _, inputs = actual_run(monkeypatch, tmp_path)
    invalid = replace(inputs[0], liquidity_context=replace(inputs[0].liquidity_context, **{field: bad}))
    assert not FlatTopBreakoutPattern().evaluate(invalid).detected


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_each_structural_ohlcv_field_requires_finite_authority(monkeypatch, tmp_path, field, bad):
    from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern
    _, _, _, _, inputs = actual_run(monkeypatch, tmp_path)
    source = inputs[0]
    rows = list(source.candles)
    rows[-3] = replace(rows[-3], **{field: bad})
    result = FlatTopBreakoutPattern().evaluate(replace(source, candles=rows))
    assert not result.detected and result.rejection_reason == "INVALID_CANDLE_DATA"


@pytest.mark.parametrize("clock", [None, datetime(2026, 9, 16, 14, 35, 30), "not-a-clock"])
def test_active_source_cannot_lose_its_original_clock(monkeypatch, tmp_path, clock):
    from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern
    _, _, _, _, inputs = actual_run(monkeypatch, tmp_path)
    result = FlatTopBreakoutPattern().evaluate(replace(inputs[0], observed_at_utc=clock))
    assert not result.detected and result.rejection_reason == "INVALID_CANDLE_TIMESTAMPS"


def test_actual_raw_formation_does_not_bypass_five_position_manager_veto(monkeypatch, tmp_path, capsys):
    """Separate synthetic manager-handoff control; no claim of natural Focus proof."""
    from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload
    from test_ross_supported_catalyst_critical_path import _saved_shape_verdict
    _, intents, _, _, _ = actual_run(monkeypatch, tmp_path)
    assert len(intents) == 1 and intents[0].decision_id is None
    row = _row("UPC", catalyst=True)
    core, _, _ = _install_runtime_harness(monkeypatch, [_payload([row], focus=[row])])
    verdict = _saved_shape_verdict(datetime.now(timezone.utc))
    monkeypatch.setattr(core, "_resolve_position_truth_cycle", lambda **kwargs: verdict)
    # Feed the real raw intent already formed above into the manager guard. This
    # neither grants a risk/artifact ID nor fabricates a detector or risk result.
    core.strategy_runner.process = lambda **kwargs: intents
    def forbidden(*args, **kwargs):
        pytest.fail("position veto must admit no canonical artifact/risk input")
    monkeypatch.setattr(core.risk_engine, "evaluate_trade_intent", forbidden)
    from src.core import orchestrator
    monkeypatch.setattr(orchestrator, "build_decision_artifact", forbidden)
    capsys.readouterr()
    assert core.run_once()
    output = capsys.readouterr().out
    assert "[PIPELINE][STRATEGY_OUTPUT] count=1" in output
    assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in output
    assert "dominant_blocking_reasons={'POSITION_TRUTH_BLOCK_NEW_ENTRIES': 1}" in output
    assert "reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY" not in output
    assert "[PIPELINE][RISK_INPUT] intents_count=0" in output
    assert intents[0].decision_id is None
    assert "ORDER_SUBMITTED" not in output
