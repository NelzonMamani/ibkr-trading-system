from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.config.runtime_config import RunMode
from src.strategies.ross_momentum.patterns.pattern_trace import (
    PatternInputSnapshotSummary,
    RossPatternTrace,
    RossPipelineStageResult,
)
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class _FakeCandle:
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class _FakeInputs:
    symbol: str
    candles: list[_FakeCandle]
    levels: object
    indicators: object
    session_context: str = "RTH_OPEN"


_ALLOWED_TERMINALS = {
    "DROPPED_AT_CONTEXT",
    "DROPPED_AT_STRUCTURE",
    "DROPPED_AT_SETUP",
    "DROPPED_AT_CONFIRMATION",
    "ARMED_WAITING_TRIGGER",
    "TRIGGER_FIRED_INTENT_EMITTED",
    "BLOCKED_AFTER_TRIGGER_BY_RISK",
    "BLOCKED_AFTER_TRIGGER_BY_EXECUTION_PRECHECK",
}


def _setup_harness(monkeypatch, *, summary: PatternInputSnapshotSummary, pattern_id: str = "P_FIRST_PULLBACK", detected: bool = True):
    strategy = RossMomentumStrategyV1()
    inputs = _FakeInputs(
        symbol="TEST",
        candles=[
            _FakeCandle(10.0, 10.2, 9.95, 10.15, 20_000),
            _FakeCandle(10.15, 10.35, 10.05, 10.25, 25_000),
            _FakeCandle(10.24, 10.45, 10.2, 10.4, 30_000),
            _FakeCandle(10.38, 10.5, 10.3, 10.45, 35_000),
        ],
        levels=SimpleNamespace(hod=10.4, lod=9.9, premarket_high=10.35),
        indicators=SimpleNamespace(ema9=10.1, ema20=10.0, vwap=10.2),
    )

    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_runtime_pattern_inputs",
        lambda **_: (inputs, []),
    )
    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_input_snapshot_summary",
        lambda **_: summary,
    )
    def _fake_run(_inputs, trace_context=None, trace_collector=None):
        trace = RossPatternTrace(
            symbol="TEST",
            cycle_id="cycle",
            strategy_key="ross_momentum",
            session_label="RTH_OPEN",
            session_phase="OPEN",
            runtime_mode="SIM",
            symbol_source="watchlist",
            pattern_id=pattern_id,
            pattern_name=pattern_id,
            setup_family_id=pattern_id,
            invoked=True,
            detected=detected,
            rejection_reason=None if detected else "no_impulse",
        )
        trace.confidence = 0.85
        if trace_collector:
            trace_collector(trace)
        return [SimpleNamespace(confidence=0.85)]

    monkeypatch.setattr(strategy._pattern_registry, "run", _fake_run)
    return strategy


def _run_once(strategy: RossMomentumStrategyV1, mode: RunMode = RunMode.SIM):
    strategy.process_watchlist(
        watchlist=[{"symbol": "TEST"}],
        snapshots={},
        session_label="RTH_OPEN",
        timestamp_utc="2026-03-25T14:35:00+00:00",
        mode=mode,
        session_phase="OPEN",
    )
    return strategy._failure_trace_collector._symbols[-1].pipeline_trace


def test_context_terminality_drop_reason(monkeypatch) -> None:
    strategy = RossMomentumStrategyV1()
    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_runtime_pattern_inputs",
        lambda **_: (None, []),
    )
    trace = _run_once(strategy)
    assert trace["final_outcome"] == "DROPPED_AT_CONTEXT"
    assert trace["context_stage"]["reason_code"] == "FAILED_TO_BUILD_INPUTS"


def test_structure_rejection_is_explicit(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(
        candle_count=2,
        last_price=10.0,
        bid=9.99,
        ask=10.01,
        spread=0.02,
        volume=150_000,
        pct_change=0.1,
        rvol=2.2,
        float_millions=10,
        has_levels=True,
        has_indicators=True,
    )
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_structure_stage = lambda **_: RossPipelineStageResult(
        stage="STRUCTURE",
        passed=False,
        status="REJECTED",
        reason_code="NO_IMPULSE",
    )
    trace = _run_once(strategy)
    assert trace["final_outcome"] == "DROPPED_AT_STRUCTURE"
    assert trace["final_reason_code"] == "NO_IMPULSE"


def test_setup_classification_selects_family(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.45, 10.44, 10.46, 0.02, 200_000, 6.2, 2.8, 12.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary, pattern_id="P_FIRST_PULLBACK")
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.4, 10.0)
    trace = _run_once(strategy)
    assert trace["setup_stage"]["passed"] is True
    assert trace["setup_stage"]["reason_code"] == "FIRST_PULLBACK"


def test_confirmation_rejection_is_terminal(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.3, 10.29, 10.31, 0.02, 200_000, 5.5, 2.1, 20.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (False, ["volume_confirmation_failed"], [])
    trace = _run_once(strategy)
    assert trace["final_outcome"] == "DROPPED_AT_CONFIRMATION"
    assert trace["confirmation_stage"]["reason_code"] == "CONFIRMATION_BLOCKED"


def test_trigger_armed_waiting_condition(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.2, 10.19, 10.21, 0.02, 220_000, 7.0, 3.0, 18.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.5, 10.0)
    trace = _run_once(strategy)
    assert trace["final_outcome"] == "ARMED_WAITING_TRIGGER"
    assert trace["trigger_stage"]["status"] == "ARMED_NOT_FIRED_YET"


def test_trigger_fired_emits_intent(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.6, 10.59, 10.61, 0.02, 240_000, 8.5, 3.2, 16.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.5, 10.0)
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "TEST"}], snapshots={}, session_label="RTH_OPEN", timestamp_utc="2026-03-25T14:35:00+00:00", mode=RunMode.SIM, session_phase="OPEN"
    )
    trace = strategy._failure_trace_collector._symbols[-1].pipeline_trace
    assert intents
    assert trace["final_outcome"] == "TRIGGER_FIRED_INTENT_EMITTED"


def test_no_silent_drop_terminal_status(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.2, 10.19, 10.21, 0.02, 220_000, 7.0, 3.0, 18.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.5, 10.0)
    trace = _run_once(strategy)
    assert trace["final_outcome"] in _ALLOWED_TERMINALS


def test_post_trigger_execution_precheck_block_trace(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.8, 10.79, 10.81, 0.02, 260_000, 9.0, 3.5, 14.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary)
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.5, 10.0)
    trace = _run_once(strategy, mode=RunMode.READ_ONLY)
    assert trace["final_outcome"] == "BLOCKED_AFTER_TRIGGER_BY_EXECUTION_PRECHECK"


def test_live_watchlist_flow_reaches_intent_on_valid_candidate(monkeypatch) -> None:
    summary = PatternInputSnapshotSummary(4, 10.8, 10.79, 10.81, 0.02, 260_000, 9.0, 3.5, 14.0, True, has_indicators=True)
    strategy = _setup_harness(monkeypatch, summary=summary, pattern_id="P_HOD_BREAK")
    strategy._data_contract_block_reasons = lambda **_: []
    strategy._evaluate_confirmation = lambda **_: (True, [], [])
    strategy._build_trade_from_pattern = lambda *_: (10.5, 10.0)
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "TEST"}], snapshots={}, session_label="RTH_OPEN", timestamp_utc="2026-03-25T14:35:00+00:00", mode=RunMode.SIM, session_phase="OPEN"
    )
    assert intents and intents[0].symbol == "TEST"
