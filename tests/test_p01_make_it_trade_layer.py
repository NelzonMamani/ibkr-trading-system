from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class EmptyRegistry:
    inactive_pattern_ids: set[str]

    @property
    def pattern_ids(self) -> list[str]:
        return []

    def run(self, inputs, *, trace_context=None, trace_collector=None) -> list[PatternResult]:
        return []


def _hod_break_bars() -> list[Candle]:
    return [
        Candle(open=10.00, high=10.06, low=9.98, close=10.04, volume=1200),
        Candle(open=10.04, high=10.12, low=10.00, close=10.10, volume=1300),
        Candle(open=10.10, high=10.22, low=10.08, close=10.20, volume=1400),
        Candle(open=10.20, high=10.32, low=10.16, close=10.30, volume=1500),
        Candle(open=10.30, high=10.44, low=10.26, close=10.40, volume=1600),
        Candle(open=10.40, high=10.56, low=10.36, close=10.52, volume=1700),
        Candle(open=10.52, high=10.70, low=10.48, close=10.66, volume=1800),
        Candle(open=10.66, high=10.86, low=10.62, close=10.82, volume=1900),
        Candle(open=10.82, high=11.04, low=10.78, close=10.98, volume=2000),
        Candle(open=10.98, high=11.20, low=10.94, close=11.14, volume=2100),
        Candle(open=11.14, high=11.38, low=11.10, close=11.30, volume=2300),
        Candle(open=11.30, high=11.52, low=11.24, close=11.46, volume=2500),
        Candle(open=11.46, high=11.58, low=11.08, close=11.20, volume=2700),
        Candle(open=11.20, high=11.50, low=11.18, close=11.42, volume=3000),
        Candle(open=11.42, high=11.66, low=11.36, close=11.60, volume=3300),
        Candle(open=11.60, high=11.84, low=11.54, close=11.78, volume=3600),
    ]


def _watchlist_row(symbol: str = "TEST") -> dict:
    return {
        "symbol": symbol,
        "promotion_reason": "watchlist",
        "session_label": "PRE",
        "last_price": 11.6,
        "bid": 11.59,
        "ask": 11.61,
        "volume": 950000,
        "rvol": 3.4,
        "float_millions": 18.0,
        "premarket_high": 11.55,
        "prior_close": 10.8,
        "pct_change": 7.4,
    }


def _snapshot(symbol: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=11.59,
        ask=11.61,
        last=11.6,
        volume=950000,
        asof_utc=datetime.now(timezone.utc),
    )


def _base_strategy(monkeypatch, tmp_path) -> RossMomentumStrategyV1:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _hod_break_bars(),
    )
    strategy = RossMomentumStrategyV1()
    strategy._failure_trace_collector = RossPatternFailureTraceCollector(evidence_root=tmp_path)
    strategy._pattern_registry = EmptyRegistry(inactive_pattern_ids=set())
    strategy._data_contract_block_reasons = lambda **kwargs: []
    return strategy


def test_runtime_strategy_entrypoint_emits_eval_start(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)

    strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-eval-start",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert "[ROSS][EVAL_START] symbol=TEST" in out
    assert "[ROSS][EVAL_CONTEXT] symbol=TEST" in out


def test_pattern_registry_or_setup_engine_produces_setup(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)

    strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-setup",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert "[ROSS][SETUP] symbol=TEST source=setup_engine" in out


def test_trigger_fired_generates_trade_intent(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)

    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-trigger-intent",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert intents
    assert intents[0].trigger_ready is True
    assert "TRADE_INTENT symbol=TEST" in out
    assert "[ROSS][INTENT_GENERATED] symbol=TEST" in out


def test_no_silent_drop_after_context(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    row = _watchlist_row()
    row["rvol"] = 0.1
    row["pct_change"] = -1.0

    intents = strategy.process_watchlist(
        watchlist=[row],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-no-silent-drop",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert "[ROSS][EVAL_CONTEXT] symbol=TEST" in out
    assert "[ROSS][SETUP] symbol=TEST source=setup_engine" in out
    assert "[ROSS][INTENT_GENERATED] symbol=TEST" in out
    assert intents


def test_data_block_does_not_force_intent(monkeypatch, tmp_path, capsys) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)
    strategy._data_contract_block_reasons = lambda **kwargs: ["MISSING_BID_ASK"]
    row = _watchlist_row()
    row["bid"] = None
    row["ask"] = None
    row["last_price"] = None

    intents = strategy.process_watchlist(
        watchlist=[row],
        snapshots={},
        session_label="PRE",
        timestamp_utc="cycle-data-block-no-force",
        mode=RunMode.SIM,
        session_phase="PRE",
    )

    out = capsys.readouterr().out
    assert intents == []
    assert "[ROSS][DATA_BLOCK] symbol=TEST" in out
    assert "[ROSS][TERMINAL] symbol=TEST category=DATA_BLOCKED" in out


def test_pr554_pipeline_trace_populated_on_live_path(monkeypatch, tmp_path) -> None:
    strategy = _base_strategy(monkeypatch, tmp_path)

    strategy.process_watchlist(
        watchlist=[_watchlist_row()],
        snapshots={"TEST": _snapshot()},
        session_label="PRE",
        timestamp_utc="cycle-trace",
        mode=RunMode.LIVE,
        session_phase="PRE",
    )

    trace = strategy._failure_trace_collector._symbols[-1]
    assert trace.context_stage["status"] == "PASS"
    assert trace.structure_stage["reason_code"] in {"VALID", "VALID_LOW_SAMPLE_SIZE"}
    assert trace.setup_stage["status"] == "PASS"
    assert trace.trigger_stage["status"] == "FIRED"
    assert trace.final_outcome is not None
    assert trace.final_reason_code is not None


def test_focus_empty_but_viable_watchlist_still_reaches_ross_evaluation(monkeypatch) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )
    observed: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        row = SimpleNamespace(symbol="AAPL", session_label="PRE", session_phase="PRE")
        return {
            "candidate_metrics": [row],
            "watchlist_k": [row],
            "watchlist_k_symbols": ["AAPL"],
            "focus_m": [],
            "focus_m_symbols": [],
            "universe_top_n": [{"symbol": "AAPL"}],
            "candidates": [row],
        }

    def _process(**kwargs):
        observed["watchlist"] = [getattr(item, "symbol", "") for item in kwargs["watchlist"]]
        return []

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(batch_snapshots=lambda symbols: ({}, []))
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = _process
        assert orchestrator.run_once() is True
        assert observed["watchlist"] == ["AAPL"]
    finally:
        set_config_overrides(None)


def test_force_session_override_propagates_to_strategy_context(monkeypatch, capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )
    observed: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        row = SimpleNamespace(symbol="AAPL", session_label="PRE", session_phase="PRE")
        return {
            "candidate_metrics": [row],
            "watchlist_k": [row],
            "watchlist_k_symbols": ["AAPL"],
            "focus_m": [row],
            "focus_m_symbols": ["AAPL"],
            "universe_top_n": [{"symbol": "AAPL"}],
            "candidates": [row],
        }

    def _process(**kwargs):
        observed["session_label"] = kwargs["session_label"]
        return []

    monkeypatch.setenv("FORCE_SESSION", "PREMARKET")
    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(batch_snapshots=lambda symbols: ({}, []))
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = _process
        assert orchestrator.run_once() is True
        out = capsys.readouterr().out
        assert "[SESSION][FORCED_OVERRIDE] requested=PREMARKET applied=PRE" in out
        assert observed["session_label"] == "PREMARKET"
    finally:
        set_config_overrides(None)
