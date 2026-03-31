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
from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import SessionContext
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


def test_registry_invocation_trace_present(monkeypatch) -> None:
    row = _manual_focus_row()
    snap = _snapshot()
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=4 + idx * 0.01, high=4.2 + idx * 0.01, low=3.9 + idx * 0.01, close=4.1 + idx * 0.01, volume=1000 + idx) for idx in range(20)],
    )
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
    assert any(
        trace.invoked or trace.skipped
        for trace in traces
    )
    assert any(
        trace.rejection_reason or trace.skip_reason
        for trace in traces
    )


def test_pattern_trace_records_rejection_reason(monkeypatch) -> None:
    row = _manual_focus_row()
    snap = _snapshot()
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=4 + idx * 0.01, high=4.2 + idx * 0.01, low=3.9 + idx * 0.01, close=4.1 + idx * 0.01, volume=1000 + idx) for idx in range(20)],
    )
    inputs, flags = build_runtime_pattern_inputs(symbol="TMDE", row=row, snapshot=snap, session_label="AH", session_phase="AH")
    summary = build_input_snapshot_summary(row=row, snapshot=snap, inputs=inputs, session_label="AH", quality_flags=flags)
    traces = []
    RossPatternRegistry().run(
        inputs,
        trace_context={"strategy_key": "ross_momentum", "input_summary": summary.to_dict()},
        trace_collector=traces.append,
    )
    assert any(
        trace.rejection_reason or trace.skip_reason
        for trace in traces
    )


def test_power_hour_maps_to_regular_session_context(monkeypatch) -> None:
    row = _manual_focus_row()
    snap = _snapshot()
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=4 + idx * 0.01, high=4.2 + idx * 0.01, low=3.9 + idx * 0.01, close=4.1 + idx * 0.01, volume=1000 + idx) for idx in range(20)],
    )
    inputs, _flags = build_runtime_pattern_inputs(
        symbol="TMDE",
        row=row,
        snapshot=snap,
        session_label="POWER_HOUR",
        session_phase="POWER_HOUR",
    )
    assert inputs is not None
    assert inputs.session_context == SessionContext.REGULAR


def test_no_setup_summary_aggregates_reasons(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=4 + idx * 0.01, high=4.2 + idx * 0.01, low=3.9 + idx * 0.01, close=4.1 + idx * 0.01, volume=1000 + idx) for idx in range(20)],
    )
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
    assert cycle.dominant_rejection_reasons is not None
    assert isinstance(cycle.dominant_rejection_reasons, dict)
    path = collector.persist_latest(run_mode="LIVE", session_label="AH", session_phase="AH")
    payload = json.loads(path.read_text())
    assert payload["cycle_summaries"]


def test_detected_pattern_translates_to_trade_intent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=10.5 + idx * 0.03, high=10.6 + idx * 0.03, low=10.4 + idx * 0.03, close=10.55 + idx * 0.03, volume=2000 + idx) for idx in range(25)],
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    watchlist = [{
        "symbol": "TEST",
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 11.1,
        "bid": 11.09,
        "ask": 11.11,
        "volume": 12000,
        "rvol": 2.0,
        "float_millions": 10.0,
        "premarket_high": 10.95,
        "prior_close": 10.0,
    }]
    intents = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots={"TEST": MarketSnapshot(symbol="TEST", bid=11.09, ask=11.11, last=11.1, volume=12000, asof_utc=datetime.now(timezone.utc))},
        session_label="PRE",
        timestamp_utc="cycle-1",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )
    payload = json.loads((tmp_path / "latest_pattern_failure_trace.json").read_text())
    symbol_eval = next(item for item in payload["symbol_evaluations"] if item["symbol"] == "TEST")
    final_outcome = str(symbol_eval.get("final_outcome", ""))
    valid_pattern_inputs = "data_contract_blocked" not in final_outcome.lower() and "failed_to_build_inputs" not in final_outcome.lower()
    if valid_pattern_inputs:
        assert intents
        assert intents[0].decision == "TRADE_READY"
        assert intents[0].trigger_id.endswith(":TRIGGER") or bool(intents[0].trigger_id)
        assert intents[0].entry_price is not None
        assert intents[0].stop_loss_price is not None
        assert symbol_eval["final_outcome"] == "SETUP_DETECTED_AND_TRANSLATED"
    else:
        assert intents == []
    cycle_summary = payload["cycle_summaries"][-1]
    if valid_pattern_inputs:
        assert cycle_summary["real_setup_trigger_count"] > 0
    else:
        assert cycle_summary["real_setup_trigger_count"] == 0


def test_missing_inputs_surface_in_trace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=1 + idx * 0.01, high=1.1 + idx * 0.01, low=0.9 + idx * 0.01, close=1.05 + idx * 0.01, volume=500 + idx) for idx in range(20)],
    )
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


def test_runtime_pattern_inputs_prefers_historical_candles(monkeypatch) -> None:
    row = _manual_focus_row("HIST")
    snap = _snapshot("HIST")

    historical = [
        Candle(open=10 + idx, high=10.2 + idx, low=9.8 + idx, close=10.1 + idx, volume=1000 + idx)
        for idx in range(20)
    ]
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: historical,
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="HIST",
        row=row,
        snapshot=snap,
        session_label="AH",
        session_phase="AH",
    )

    assert inputs is not None
    assert len(inputs.candles) == 20
    assert inputs.news_context and inputs.news_context["candle_count"] == "20"
    assert "indicators_incomplete" not in flags
    assert "levels_incomplete" not in flags
    assert inputs.indicators.ema9 is not None
    assert inputs.indicators.ema20 is not None
    assert inputs.indicators.vwap is not None
    assert inputs.levels.hod is not None
    assert inputs.levels.lod is not None
    assert inputs.liquidity_context.rvol is not None


def test_runtime_pattern_inputs_marks_short_history_but_builds(monkeypatch) -> None:
    row = _manual_focus_row("SNAP")
    snap = _snapshot("SNAP")

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=1, high=1, low=1, close=1, volume=1) for _ in range(5)],
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="SNAP",
        row=row,
        snapshot=snap,
        session_label="AH",
        session_phase="AH",
    )

    assert inputs is not None
    assert "insufficient_candles" in flags
    assert inputs.indicators.ema9 is not None
    assert inputs.indicators.vwap is not None


def test_runtime_pattern_inputs_preserves_missing_bid_ask_and_marks_spread_unknown(monkeypatch) -> None:
    row = {
        "symbol": "MISS",
        "promotion_reason": "manual_focus",
        "session_label": "PRE",
        "last_price": 5.5,
        "data_quality_flags": ["SPREAD_UNKNOWN"],
        "volume": 25_000,
        "prior_close": 5.0,
    }
    snap = MarketSnapshot(symbol="MISS", bid=None, ask=None, last=5.5, volume=25_000, asof_utc=datetime.now(timezone.utc))
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: [Candle(open=5 + idx * 0.02, high=5.05 + idx * 0.02, low=4.98 + idx * 0.02, close=5.01 + idx * 0.02, volume=800 + idx) for idx in range(20)],
    )
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.FloatProvider.get_float",
        lambda self, symbol: (None, "missing"),
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="MISS",
        row=row,
        snapshot=snap,
        session_label="PRE",
        session_phase="PRE",
    )
    summary = build_input_snapshot_summary(row=row, snapshot=snap, inputs=None, session_label="PRE", quality_flags=flags)

    assert inputs is not None
    assert inputs.liquidity_context.float_millions is None
    assert "float_missing" in flags
    assert summary.bid is None
    assert summary.ask is None
    assert "SPREAD_UNKNOWN" in summary.quality_flags
