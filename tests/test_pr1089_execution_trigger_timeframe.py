from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.config.runtime_config import RunMode
from src.core.engines.trigger_engine import TriggerEngine
from src.strategies.ross_momentum.patterns.pattern_inputs import build_authoritative_pattern_inputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _candles, _snapshot, _watchlist_row, _reset_config,
)
from test_pr1089_pullback_continuity_and_provenance import _case, _synthetic_complete_registry


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    from ibapi.client import EClient
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("broker call forbidden")
    for name in ("connect", "placeOrder", "cancelOrder"):
        monkeypatch.setattr(EClient, name, forbidden)
    yield
    assert calls == []


def streams(family, *, session="RTH_OPEN", primary_fire=False, execution_fire=True):
    pattern, _, rows, _, fire, _ = _case(family)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    if primary_fire:
        rows = rows[:-1] + [fire]
    primary = _candles(rows, end=end)
    level = 10.44 if family == "THREE_BAR_PULLBACK" else 10.59
    low = 10.20 if family == "THREE_BAR_PULLBACK" else 10.44
    # Genuine 10s observations, with volumes measured per 10s interval.
    ten_rows = [(level - .05, level - .01, low, level - .04, 100)] * 25
    if execution_fire:
        ten_rows[-1] = (level - .04, level + .06, low, level + .04, 200)
    ten = _candles(ten_rows, end=end + timedelta(seconds=10), step_seconds=10)
    return pattern, {"1m": primary, "10s": ten, "5m": _candles(rows, end=end, step_seconds=300)}


def run_strategy(monkeypatch, tmp_path, family, data, *, session="RTH_OPEN", symbol="UPC",
                 synthetic_complete=True):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    registry = _synthetic_complete_registry(_case(family)[0]) if synthetic_complete else RossPatternRegistry()
    registry._patterns = [_case(family)[0]]
    strategy._pattern_registry = registry
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *, timeframe="1m", **kwargs: data.get(timeframe, []),
    )
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row(symbol=symbol)],
        snapshots={symbol: _snapshot(symbol=symbol)}, session_label=session,
        timestamp_utc="execution-cycle", mode=RunMode.READ_ONLY, session_phase=session,
    )
    trace = strategy._failure_trace_collector._symbols[-1]
    return strategy, intents, trace.input_summary.get("trigger_candidates", [])


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_intraminute_execution_break_fires_from_real_strategy(monkeypatch, tmp_path, family):
    pattern, data = streams(family)
    inputs = build_authoritative_pattern_inputs(symbol="UPC", session_label="RTH_OPEN", timeframe_candles=data)
    result = pattern.evaluate(inputs)
    assert result.detected
    assert result.setup_metadata["breakout_volume_confirmed"] is not True
    strategy, intents, triggers = run_strategy(monkeypatch, tmp_path, family, data)
    assert len(intents) == 1
    assert intents[0].target_model == "SYNTHETIC_DOWNSTREAM_GATE_TARGET"
    assert strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]
    trigger = next(t for t in triggers if t["setup_family_id"] == family)
    assert trigger["trigger_ready_now"]
    assert trigger["trigger_price_reference"] == result.trigger_level
    assert trigger["invalidation_price_reference"] == result.invalidation_level
    evidence = trigger["execution_stream"]
    assert evidence["structure_timeframe"] == "1m"
    assert evidence["execution_trigger_timeframe"] == "10s"
    assert evidence["volume_confirmation_timeframe"] == "10s"
    assert evidence["candle_stream"] == "timeframe_candles[10s]"
    assert evidence["stream_provenance"] == "PRESENT"
    assert evidence["timeframe_substitution"] is False
    assert evidence["volume_baseline"] == 100
    assert evidence["current_volume"] == 200


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_primary_break_cannot_replace_execution_break(monkeypatch, tmp_path, family):
    _, data = streams(family, primary_fire=True, execution_fire=False)
    _, intents, triggers = run_strategy(monkeypatch, tmp_path, family, data)
    assert intents == []
    trigger = next(t for t in triggers if t["setup_family_id"] == family)
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_reason"] == "awaiting_pullback_break"


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
@pytest.mark.parametrize("failure", ["weak", "missing", "stale", "insufficient", "nan", "bad_ohlc", "gap", "no_baseline"])
def test_execution_evidence_fails_closed(monkeypatch, tmp_path, family, failure):
    _, data = streams(family)
    ten = data["10s"]
    if failure == "weak":
        ten[-1] = replace(ten[-1], volume=100)
    elif failure == "missing":
        data.pop("10s")
    elif failure == "stale":
        data["10s"] = [replace(c, timestamp=c.timestamp - timedelta(minutes=10)) for c in ten]
    elif failure == "insufficient":
        data["10s"] = ten[-1:]
    elif failure == "nan":
        ten[-1] = replace(ten[-1], volume=float("nan"))
    elif failure == "bad_ohlc":
        ten[-1] = replace(ten[-1], high=1)
    elif failure == "gap":
        del ten[-2]
    else:
        data["10s"] = ten[-2:]
    strategy, intents, triggers = run_strategy(monkeypatch, tmp_path, family, data)
    assert intents == []
    assert not any(t["trigger_ready_now"] for t in triggers if t["setup_family_id"] == family)

    family_triggers = [t for t in triggers if t["setup_family_id"] == family]
    if failure == "missing":
        # The earlier required-input gate must name the unavailable stream;
        # absence of an entry alone would be a vacuous completeness assertion.
        assert not family_triggers
        traces = strategy._failure_trace_collector._symbols[-1].pattern_traces
        assert any("pr4_input_block" in (t.rejection_reason or "")
                   and "timeframe:10s=MISSING" in (t.rejection_reason or "") for t in traces)
    else:
        expected = {"weak":"breakout_volume_confirmation_failed",
                    "stale":"execution_volume_history_missing",
                    "insufficient":"execution_stream_insufficient",
                    "nan":"execution_stream_malformed_candle",
                    "bad_ohlc":"execution_stream_malformed_candle",
                    "gap":"execution_stream_insufficient",
                    "no_baseline":"execution_volume_history_missing"}[failure]
        assert family_triggers and all(t["trigger_reason"] == expected for t in family_triggers)
        assert strategy.last_symbol_terminal_outcomes["UPC"]["reason"] == expected


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_steady_session_uses_actual_one_minute_stream(monkeypatch, tmp_path, family):
    _, data = streams(family, primary_fire=True, execution_fire=False)
    strategy, intents, triggers = run_strategy(monkeypatch, tmp_path, family, data, session="RTH_MID")
    assert len(intents) == 1
    assert intents[0].target_model == "SYNTHETIC_DOWNSTREAM_GATE_TARGET"
    assert strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]
    evidence = next(t for t in triggers if t["setup_family_id"] == family)["execution_stream"]
    assert evidence["execution_trigger_timeframe"] == "1m"
    assert evidence["volume_confirmation_timeframe"] == "1m"
    assert evidence["candle_stream"] == "timeframe_candles[1m]"


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
@pytest.mark.parametrize("event", ["consumed", "invalidated"])
def test_execution_history_cannot_refire_or_recover(monkeypatch, tmp_path, family, event):
    _, data = streams(family)
    ten = data["10s"]
    level = 10.44 if family == "THREE_BAR_PULLBACK" else 10.59
    if event == "invalidated":
        ten[-1] = replace(ten[-1], low=10.0)
    ten.append(replace(ten[-1], close=level - .02, high=level, low=level - .03,
                       open=level - .02, volume=100, timestamp=ten[-1].timestamp + timedelta(seconds=10)))
    ten.append(replace(ten[-1], close=level + .03, high=level + .04, volume=200,
                       timestamp=ten[-1].timestamp + timedelta(seconds=10)))
    _, intents, triggers = run_strategy(monkeypatch, tmp_path, family, data)
    assert intents == []
    trigger = next(t for t in triggers if t["setup_family_id"] == family)
    assert trigger["trigger_reason"] == (
        "pullback_breakout_already_consumed" if event == "consumed" else "structural_invalidation_breached"
    )


def test_missing_execution_stream_preserves_other_symbol(monkeypatch, tmp_path):
    family = "THREE_BAR_PULLBACK"
    _, data = streams(family)
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    registry = _synthetic_complete_registry(_case(family)[0])
    strategy._pattern_registry = registry
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda *, symbol, timeframe="1m", **kwargs: [] if symbol == "BBB" and timeframe == "10s" else data[timeframe],
    )
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row(symbol=s) for s in ("AAA", "BBB")],
        snapshots={s: _snapshot(symbol=s) for s in ("AAA", "BBB")},
        session_label="RTH_OPEN", session_phase="RTH_OPEN",
        timestamp_utc="mixed-cycle", mode=RunMode.READ_ONLY,
    )
    assert [intent.symbol for intent in intents] == ["AAA"]
    assert intents[0].target_model == "SYNTHETIC_DOWNSTREAM_GATE_TARGET"
    assert strategy.last_symbol_terminal_outcomes["AAA"]["trigger_ready_now"]
    assert strategy.last_symbol_terminal_outcomes["AAA"]["intent_emitted"]
    assert strategy.last_symbol_terminal_outcomes["BBB"]["intent_emitted"] is False


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_primary_history_does_not_consume_execution_entry(monkeypatch, tmp_path, family):
    _, data = streams(family, primary_fire=True)
    primary = data["1m"]
    # A previous primary breakout is not evidence of an execution-stream firing.
    wait = _case(family)[3]
    primary.append(_candles([wait], end=primary[-1].timestamp + timedelta(minutes=1))[0])
    # Keep the execution history within freshness and covering the original window.
    level = 10.44 if family == "THREE_BAR_PULLBACK" else 10.59
    low = 10.20 if family == "THREE_BAR_PULLBACK" else 10.44
    rows = [(level - .05, level - .01, low, level - .04, 100)] * 37
    rows[-1] = (level - .04, level + .06, low, level + .04, 200)
    data["10s"] = _candles(rows, end=primary[-1].timestamp, step_seconds=10)
    strategy, intents, _ = run_strategy(monkeypatch, tmp_path, family, data)
    assert len(intents) == 1
    assert intents[0].target_model == "SYNTHETIC_DOWNSTREAM_GATE_TARGET"
    assert strategy.last_symbol_terminal_outcomes["UPC"]["intent_emitted"]


@pytest.mark.parametrize("failure,reason", [
    ("missing", "execution_stream_missing"),
    ("stale", "execution_stream_stale"),
    ("policy", "execution_stream_policy_blocked"),
    ("masquerade", "execution_volume_history_missing"),
])
def test_registered_engine_preserves_explicit_stream_failure(failure, reason):
    from test_pr1082_trigger_to_intent_terminal_semantics import _trigger_payload
    pattern, data = streams("THREE_BAR_PULLBACK")
    inputs = build_authoritative_pattern_inputs(symbol="UPC", session_label="RTH_OPEN", timeframe_candles=data)
    setup = _trigger_payload(pattern.evaluate(inputs))
    setup["execution_stream"] = {
        "structure_timeframe": "1m", "execution_trigger_timeframe": "10s",
        "volume_confirmation_timeframe": "10s", "candle_stream": "timeframe_candles[10s]",
        "stream_provenance": "PRESENT", "policy_action": "IGNORE", "timeframe_substitution": False,
    }
    candles = data["10s"]
    if failure in ("missing", "stale"):
        setup["execution_stream"]["stream_provenance"] = failure.upper()
        if failure == "missing":
            candles = []
    elif failure == "policy":
        setup["execution_stream"]["policy_action"] = "BLOCK"
    else:
        candles = data["1m"]
    trigger = TriggerEngine().evaluate_triggers(
        symbol="UPC", candles=candles, setups=[setup], levels={}, structure={},
    )[0]
    assert trigger["trigger_state"] == "BLOCKED"
    assert trigger["trigger_reason"] == reason
    assert trigger["execution_stream"]["timeframe_substitution"] is False


@pytest.mark.parametrize("family", ["THREE_BAR_PULLBACK", "SECOND_PULLBACK"])
def test_real_targetless_pullback_remains_ineligible_before_selection(monkeypatch, tmp_path, capsys, family):
    pattern, data = streams(family)
    result = pattern.evaluate(build_authoritative_pattern_inputs(
        symbol="UPC", session_label="RTH_OPEN", timeframe_candles=data))
    assert result.detected and result.target_suggestion is None
    strategy, intents, _ = run_strategy(monkeypatch, tmp_path, family, data, synthetic_complete=False)
    assert intents == []
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    assert terminal["terminal_stage"] == "decision" and not terminal["intent_emitted"]
    assert terminal["reason"] == "all_detected_candidates_rejected"
    assert "reason=missing_target" in capsys.readouterr().out
