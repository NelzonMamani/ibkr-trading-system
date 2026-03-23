from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_trace import (
    RossPatternFailureTraceCollector,
    RossSymbolTrace,
    build_input_snapshot_summary,
    build_runtime_pattern_inputs,
)
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _manual_focus_row(symbol: str = "TMDE") -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "manual_focus",
        "session_label": "AH",
        "last_price": 4.21,
        "bid": 4.2,
        "ask": 4.22,
        "spread": 0.02,
        "volume": 120000,
        "pct_change": 7.1,
        "rvol": 0.8,
        "float_millions": 12.5,
    }


def _snapshot(symbol: str = "TMDE") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=4.2,
        ask=4.22,
        last=4.21,
        volume=120000,
        asof_utc=datetime.now(timezone.utc),
    )


def test_registry_invocation_trace_present() -> None:
    row = _manual_focus_row()
    snap = _snapshot()
    inputs, flags = build_runtime_pattern_inputs(
        symbol="TMDE",
        row=row,
        snapshot=snap,
        session_label="AH",
        session_phase="AH",
    )
    summary = build_input_snapshot_summary(row=row, snapshot=snap, inputs=inputs, session_label="AH", quality_flags=flags)
    traces = []
    results = RossPatternRegistry().run(
        inputs,
        trace_context={
            "cycle_id": "cycle-1",
            "strategy_key": "ross_momentum",
            "session_label": "AH",
            "session_phase": "AH",
            "runtime_mode": "LIVE",
            "symbol_source": "manual_focus",
            "input_summary": summary.to_dict(),
        },
        trace_collector=traces.append,
    )
    assert traces
    assert len(traces) == len(results)
    assert all(trace.invoked for trace in traces)
    assert any(trace.rejection_reason for trace in traces)


def test_pattern_trace_records_rejection_reason() -> None:
    row = _manual_focus_row()
    snap = _snapshot()
    inputs, flags = build_runtime_pattern_inputs(symbol="TMDE", row=row, snapshot=snap, session_label="AH", session_phase="AH")
    summary = build_input_snapshot_summary(row=row, snapshot=snap, inputs=inputs, session_label="AH", quality_flags=flags)
    traces = []
    RossPatternRegistry().run(
        inputs,
        trace_context={"strategy_key": "ross_momentum", "input_summary": summary.to_dict()},
        trace_collector=traces.append,
    )
    assert any(trace.rejection_reason in {"insufficient candles", "not regular session"} for trace in traces)


def test_no_setup_summary_aggregates_reasons(tmp_path: Path) -> None:
    collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    symbol_trace = RossSymbolTrace(
        symbol="TMDE",
        cycle_id="cycle-1",
        strategy_key="ross_momentum",
        session_label="AH",
        session_phase="AH",
        runtime_mode="LIVE",
        symbol_source="manual_focus",
        final_outcome="NO_SETUP:no_detected_patterns",
    )
    row = _manual_focus_row()
    snap = _snapshot()
    inputs, flags = build_runtime_pattern_inputs(symbol="TMDE", row=row, snapshot=snap, session_label="AH", session_phase="AH")
    summary = build_input_snapshot_summary(row=row, snapshot=snap, inputs=inputs, session_label="AH", quality_flags=flags)
    traces = []
    RossPatternRegistry().run(inputs, trace_context={"strategy_key": "ross_momentum", "input_summary": summary.to_dict()}, trace_collector=traces.append)
    symbol_trace.pattern_traces = traces
    collector.record_symbol(symbol_trace)
    cycle = collector.build_cycle_summary(
        cycle_id="cycle-1",
        strategy_key="ross_momentum",
        session_label="AH",
        session_phase="AH",
        runtime_mode="LIVE",
        symbol_traces=[symbol_trace],
        real_setup_trigger_count=0,
        synthetic_forced_intents=0,
    )
    assert cycle.pattern_invocations_total == len(traces)
    assert cycle.dominant_rejection_reasons
    path = collector.persist_latest(run_mode="LIVE", session_label="AH", session_phase="AH")
    payload = json.loads(path.read_text())
    assert payload["cycle_summaries"]


def test_detected_pattern_translates_to_trade_intent(tmp_path: Path) -> None:
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    watchlist = [{
        "symbol": "TEST",
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 11.1,
        "bid": 11.09,
        "ask": 11.11,
        "volume": 3000,
        "rvol": 2.0,
        "float_millions": 10.0,
        "premarket_high": 10.95,
        "prior_close": 10.0,
    }]
    intents = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={"TEST": MarketSnapshot(symbol="TEST", bid=11.09, ask=11.11, last=11.1, volume=3000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="cycle-1",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )
    assert intents
    assert all(intent.pattern_name for intent in intents)
    payload = json.loads((tmp_path / "latest_pattern_failure_trace.json").read_text())
    symbol_eval = next(item for item in payload["symbol_evaluations"] if item["symbol"] == "TEST")
    assert symbol_eval["detected_pattern_ids"]
    assert not symbol_eval["dropped_detected_pattern_ids"]
    assert symbol_eval["final_outcome"] == "SETUP_DETECTED_AND_TRANSLATED"
    cycle_summary = payload["cycle_summaries"][-1]
    assert cycle_summary["real_setup_trigger_count"] > 0


def test_missing_inputs_surface_in_trace(tmp_path: Path) -> None:
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy.process_watchlist(
        watchlist=[{"symbol": "OCGN", "promotion_reason": "manual_focus", "session_label": "AH"}],
        snapshots={"OCGN": MarketSnapshot(symbol="OCGN", bid=None, ask=None, last=None, volume=None, asof_utc=datetime.now(timezone.utc))},
        session_label="AH",
        timestamp_utc="cycle-2",
        mode=RunMode.LIVE,
        session_phase="AH",
    )
    payload = json.loads((tmp_path / "latest_pattern_failure_trace.json").read_text())
    symbol_eval = next(item for item in payload["symbol_evaluations"] if item["symbol"] == "OCGN")
    assert "missing_last_price" in symbol_eval["input_summary"]["quality_flags"]
    assert symbol_eval["manual_focus"] is True
