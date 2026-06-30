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
from src.strategies.ross_momentum.runner import RossMomentumRunner
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
        Candle(open=10.8, high=10.9, low=10.75, close=10.88, volume=1200),
        Candle(open=10.88, high=11.0, low=10.84, close=10.98, volume=1500),
        Candle(open=10.98, high=11.15, low=10.95, close=11.10, volume=1900),
        Candle(open=11.10, high=11.28, low=11.05, close=11.22, volume=2400),
        Candle(open=11.22, high=11.42, low=11.18, close=11.36, volume=2900),
        Candle(open=11.36, high=11.60, low=11.32, close=11.58, volume=3600),
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


def test_ross_runner_explicit_focus_skips_non_focus_rows(capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )
    observed: dict[str, object] = {}

    try:
        runner = RossMomentumRunner()

        def _process(**kwargs):
            observed["watchlist"] = [row.get("symbol") for row in kwargs["watchlist"]]
            return []

        runner.strategy.process_watchlist = _process
        result = runner.run(
            {
                "watchlist": [
                    {"symbol": "AAPL", "focus_m_symbols": ["AAPL"]},
                    {"symbol": "MSFT", "focus_m_symbols": ["AAPL"]},
                ],
                "snapshots": {},
                "session_label": "PRE",
                "timestamp_utc": "cycle-explicit-focus",
                "mode": RunMode.PAPER,
                "session_phase": "PRE",
            }
        )

        assert result["trade_intents"] == []
        assert result["trade_ready_count"] == 0
        assert observed["watchlist"] == ["AAPL"]
        output = capsys.readouterr().out
        assert "[ROSS][FOCUS][SKIP] symbol=MSFT reason=NOT_IN_FOCUS_LIST execution_ineligible=true" in output
        assert "[ROSS][FOCUS][SKIP] symbol=AAPL" not in output
    finally:
        set_config_overrides(None)


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
    assert trace.structure_stage["reason_code"] == "STRUCTURE_COMPRESSED_IN_MAKE_IT_TRADE_LAYER"
    assert trace.setup_stage["status"] == "PASS"
    assert trace.trigger_stage["status"] == "FIRED"
    assert trace.final_outcome is not None
    assert trace.final_reason_code is not None


def test_focus_empty_viable_watchlist_stays_diagnostic_only_in_paper(monkeypatch, capsys) -> None:
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
    monkeypatch.setattr(CoreOrchestrator, "_resolve_tha_decisions", lambda self, strategy_inputs, now_utc: {})
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(batch_snapshots=lambda symbols: ({}, []))
        orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
        orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = _process
        assert orchestrator.run_once() is True
        assert observed == {}
        output = capsys.readouterr().out
        assert "[ROSS][FOCUS_AUTHORITY] official_focus_count=0" in output
        assert "[ROSS][NO_TRADE] reason=NO_FOCUS_CANDIDATES" in output
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
