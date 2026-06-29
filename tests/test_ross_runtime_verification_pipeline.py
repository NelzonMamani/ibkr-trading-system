from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.models.data_models import TradeIntent
from src.scanner.result_models import CandidateMetrics


def _candidate(symbol: str, rank: float) -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol,
        con_id=1,
        exchange="SMART",
        session_label="PRE",
        session_phase="PRE",
        last_price=10.0,
        prev_close=9.0,
        ref_close_rth=9.0,
        reference_price=9.0,
        reference_label="PRE",
        reference_source="TEST",
        reference_quality_tier="PRIMARY",
        reference_resolved=True,
        gap_pct=5.0,
        pct_change=10.0 - rank,
        pct_change_resolved=10.0 - rank,
        pct_change_qualification_usable=True,
        pct_change_execution_usable=True,
        pct_change_source_quality="PRIMARY",
        pct_change_degraded=False,
        pct_change_synthetic=False,
        pct_change_failure_reason=None,
        gap_pct_resolved=5.0,
        gap_source="TEST",
        context_status="LIVE",
        execution_ready=True,
        prep_only=False,
        live_rvol_deferred=False,
        prep_seeded=True,
        live_confirmation_pending=False,
        watchlist_source="TEST",
        promotion_reason="TEST",
        ibkr_change_pct=None,
        pct_source="TEST",
        open_relative_pct_change=None,
        hod_pct=1.0,
        rvol=3.0,
        rvol_discovery=3.0,
        rvol_phase=3.0,
        phase_volume_ratio=1.0,
        relative_volume=3.0,
        avg_volume_20d=100000,
        adv20_resolved=True,
        degraded_adv20=False,
        adv20_source="TEST",
        rvol_status="RESOLVED",
        rvol_failure_reason=None,
        rvol_degraded=False,
        rvol_qualification_usable=True,
        rvol_execution_usable=True,
        degraded_rvol_gate_bypass=False,
        float_shares=10000000,
        float_source="cache",
        float_asof="2026-01-01T00:00:00+00:00",
        float_cache_hit=True,
        float_millions=10.0,
        volume=200000,
        premarket_volume=50000,
        dollar_volume=1_000_000.0,
        bid=10.0,
        ask=10.01,
        spread=0.01,
        spread_pct=0.1,
        halted=False,
        ssr=False,
        catalyst_present=True,
        catalyst_summary="test",
        news_count=1,
        fresh_news_count=1,
        stale_news_count=0,
        top_news_title="test",
        top_news_age_hours=0.1,
        top_news_catalyst_tag="NEWS",
        news_source_mode="TEST",
        news_asof="2026-01-01T00:00:00+00:00",
        data_quality_ok=True,
        data_quality_flags=[],
        drop_reasons=[],
        rank_score=rank,
        rank_components={"score": rank},
        timestamp_utc="2026-01-01T00:00:00+00:00",
        gate_checks={},
    )


def test_runtime_pre_session_triggers_preparation(monkeypatch):
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": False})
    calls: list[str] = []

    def _prep(self):
        calls.append("prep")

    monkeypatch.setattr("src.config.system_config.get_current_market_session", lambda *a, **k: "PRE")
    monkeypatch.setattr(CoreOrchestrator, "run_preparation_mode", _prep)
    monkeypatch.setattr(CoreOrchestrator, "run_once", lambda self: True)

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.run_forever(cycle_sleep_seconds=0, max_cycles=1)
        assert calls == ["prep"]
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_emits_required_trace_stages(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
        }
    )
    stages: list[str] = []

    def _scanner_cycle(**kwargs):
        c1 = _candidate("AAPL", 10.0)
        c2 = _candidate("MSFT", 9.0)
        return {
            "candidate_metrics": [c1, c2],
            "universe_top_n": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
            "candidates": [],
        }

    def _trace_event(stage, payload, **kwargs):
        stages.append(stage)
        return {"stage": stage, "payload": payload}

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.trace_bus.trace_event = _trace_event  # type: ignore[assignment]
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = lambda **kwargs: []

        assert orchestrator.run_once() is True
        output = capsys.readouterr().out
        for required in [
            "WATCHLIST_CREATED",
            "FOCUS_LIST_CREATED",
            "NO_SETUP",
            "ORDER_SIMULATED",
            "PATTERN_EVAL",
        ]:
            assert required in stages

        assert "[PIPELINE][STRATEGY_OUTPUT]" in output
        assert "[TRADE_PATH][FINAL]" in output
        assert "[ROSS][EVALUATE][START] symbol=AAPL" in output
        assert "[TRADE_PATH][PATTERN] symbol=AAPL verdict=NO_PATTERN_DETECTED" in output
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_accepts_setup_detected_as_valid_outcome(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
        }
    )
    stages: list[str] = []

    def _scanner_cycle(**kwargs):
        c1 = _candidate("AAPL", 10.0)
        c2 = _candidate("MSFT", 9.0)
        return {
            "candidate_metrics": [c1, c2],
            "universe_top_n": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
            "candidates": [],
        }

    def _trace_event(stage, payload, **kwargs):
        stages.append(stage)
        return {"stage": stage, "payload": payload}

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.trace_bus.trace_event = _trace_event  # type: ignore[assignment]
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = lambda **kwargs: [
            TradeIntent(
                symbol="AAPL",
                direction="LONG",
                strategy_name="ross_momentum",
                confidence=0.9,
                rationale="deterministic test",
            )
        ]

        assert orchestrator.run_once() is True
        output = capsys.readouterr().out
        for required in [
            "WATCHLIST_CREATED",
            "FOCUS_LIST_CREATED",
            "SETUP_DETECTED",
            "CONFIRMATION_PASS",
            "TRIGGER_READY",
            "INTENT_EMITTED",
            "RISK_APPROVED",
            "ORDER_SIMULATED",
            "SESSION_BLOCK",
        ]:
            assert required in stages

        assert "[PIPELINE][STRATEGY_OUTPUT]" in output
        assert "[TRADE_PATH][FINAL]" in output
        assert "[ROSS][EVALUATE][START] symbol=AAPL" in output
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_routes_ross_through_watchlist_processor(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        }
    )
    calls: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        c1 = replace(_candidate("AAPL", 10.0), session_label="AH", session_phase="AH")
        c2 = replace(_candidate("MSFT", 9.0), session_label="AH", session_phase="AH")
        return {
            "candidate_metrics": [c1, c2],
            "watchlist_k": [c1, c2],
            "watchlist_k_symbols": ["AAPL", "MSFT"],
            "focus_m": [c1],
            "focus_m_symbols": ["AAPL"],
            "universe_top_n": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
            "candidates": [c1, c2],
        }

    def _process(**kwargs):
        calls["process_watchlist"] = [getattr(row, "symbol", None) for row in kwargs["watchlist"]]
        calls["execution_allowed"] = kwargs["execution_allowed"]
        calls["execution_ready"] = kwargs["execution_ready"]
        calls["prep_only"] = kwargs["prep_only"]
        return [
            TradeIntent(
                symbol="AAPL",
                direction="LONG",
                strategy_name="ross_momentum",
                confidence=0.9,
                rationale="watchlist processor path",
            )
        ]

    def _generate(*args, **kwargs):
        calls["generate_trade_intents"] = True
        return []

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_tha_decisions", lambda self, strategy_inputs, now_utc: {})

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
        orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = _process
        orchestrator.strategy_runner.generate_trade_intents = _generate

        assert orchestrator.run_once() is True
        assert set(calls["process_watchlist"]) == {"AAPL"}
        assert calls["execution_allowed"] is False
        assert calls["execution_ready"] is False
        assert calls["prep_only"] is True
        assert "generate_trade_intents" not in calls
        output = capsys.readouterr().out
        assert "[VALIDATION_OVERRIDE]" not in output
        assert "[STRATEGY][FORCED_EXECUTION]" not in output
        assert "[STRATEGY][DIAGNOSTIC] invoking StrategyRunner reason=SESSION_RESTRICTED execution_ineligible=true" in output
    finally:
        set_config_overrides(None)


def test_session_execution_allowlist_blocks_closed_off_hours_and_unknown_labels():
    for session_label in [
        "",
        "NONE",
        "UNKNOWN",
        "NA",
        "N/A",
        "CLOSED",
        "MARKET_CLOSED",
        "WEEKEND",
        "OVN",
        "OVERNIGHT",
        "AH",
        "AFTER_HOURS",
    ]:
        assert CoreOrchestrator._session_execution_allowed(session_label) is False

    for session_label in [
        "PRE",
        "PREMARKET",
        "RTH_OPEN",
        "OPENING_0_30",
        "RTH_MID",
        "REGULAR",
        "RTH_LATE",
        "POWER_HOUR",
    ]:
        assert CoreOrchestrator._session_execution_allowed(session_label) is True


def test_runtime_pipeline_keeps_overnight_session_non_executable(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "OVN",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        }
    )
    calls: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        c1 = replace(_candidate("AAPL", 10.0), session_label="OVN", session_phase="OVN")
        c2 = replace(_candidate("MSFT", 9.0), session_label="OVN", session_phase="OVN")
        return {
            "candidate_metrics": [c1, c2],
            "watchlist_k": [c1, c2],
            "watchlist_k_symbols": ["AAPL", "MSFT"],
            "focus_m": [c1],
            "focus_m_symbols": ["AAPL"],
            "universe_top_n": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
            "candidates": [c1, c2],
        }

    def _process(**kwargs):
        calls["process_watchlist"] = [getattr(row, "symbol", None) for row in kwargs["watchlist"]]
        calls["execution_allowed"] = kwargs["execution_allowed"]
        calls["execution_ready"] = kwargs["execution_ready"]
        calls["prep_only"] = kwargs["prep_only"]
        return []

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_tha_decisions", lambda self, strategy_inputs, now_utc: {})

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
        orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
        orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        orchestrator.strategy_runner.process = _process

        assert orchestrator.run_once() is True
        assert set(calls["process_watchlist"]) == {"AAPL"}
        assert calls["execution_allowed"] is False
        assert calls["execution_ready"] is False
        assert calls["prep_only"] is True
        output = capsys.readouterr().out
        assert "[STRATEGY][DIAGNOSTIC] invoking StrategyRunner reason=SESSION_RESTRICTED execution_ineligible=true" in output
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_falls_back_to_watchlist_when_focus_empty(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
        }
    )
    calls: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        c1 = _candidate("AAPL", 10.0)
        c2 = _candidate("MSFT", 9.0)
        c3 = _candidate("NVDA", 8.0)
        c4 = _candidate("TSLA", 7.0)
        return {
            "candidate_metrics": [c1, c2, c3, c4],
            "watchlist_k": [c1, c2, c3, c4],
            "watchlist_k_symbols": ["AAPL", "MSFT", "NVDA", "TSLA"],
            "focus_m": [],
            "focus_m_symbols": [],
            "universe_top_n": [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}, {"symbol": "TSLA"}],
            "candidates": [c1, c2, c3, c4],
        }

    def _process(**kwargs):
        calls["process_watchlist"] = [getattr(row, "symbol", None) for row in kwargs["watchlist"]]
        return []

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_tha_decisions", lambda self, strategy_inputs, now_utc: {})

    try:
        sim_orchestrator = CoreOrchestrator()
        sim_orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        sim_orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
        sim_orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
        sim_orchestrator._merge_focus_candidates = lambda **kwargs: []
        sim_orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        sim_orchestrator.strategy_runner.process = _process

        assert sim_orchestrator.run_once() is True
        assert calls["process_watchlist"] == ["AAPL", "MSFT", "NVDA"]
        output = capsys.readouterr().out
        assert "[FOCUS][SELECTED] symbols=['AAPL', 'MSFT', 'NVDA']" in output
        assert "[FALLBACK][ENGAGED] reason=EMPTY_FOCUS fallback_symbols=['AAPL', 'MSFT', 'NVDA']" in output
        assert "[ROSS][PROCESS_START]" in output

        calls.clear()
        set_config_overrides(
            {
                "RUN_MODE": "PAPER",
                "EXECUTION_ENABLED": False,
                "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
                "SELECTED_STRATEGY": "ross_momentum",
                "SESSION_PHASE_OVERRIDE": "PREMARKET",
                "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
                "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            }
        )
        paper_orchestrator = CoreOrchestrator()
        paper_orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        paper_orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
        paper_orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
        paper_orchestrator._merge_focus_candidates = lambda **kwargs: []
        paper_orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
        paper_orchestrator.strategy_runner.process = _process

        assert paper_orchestrator.run_once() is True
        assert calls == {}
        output = capsys.readouterr().out
        assert "[ROSS][FOCUS_AUTHORITY] official_focus_count=0 diagnostic_focus_count=4 source=WATCHLIST_DIAGNOSTIC" in output
        assert "[ROSS][FOCUS_HANDOFF] watchlist=4 official_focus_count=0 executable_focus_count=0 diagnostic_only=true execution_ineligible=true" in output
        assert "[ROSS][NO_TRADE] reason=NO_FOCUS_CANDIDATES" in output
        assert "[PIPELINE][FOCUS] count=0 symbols=[]" in output
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_manual_focus_reaches_strategy_handoff_when_auto_focus_empty(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        }
    )
    calls: dict[str, object] = {}

    def _scanner_cycle(**kwargs):
        c1 = replace(_candidate("BNRG", 10.0), session_label="PRE", session_phase="PRE")
        c2 = replace(_candidate("SBEV", 9.0), session_label="PRE", session_phase="PRE")
        return {
            "candidate_metrics": [c1, c2],
            "watchlist_k": [c1, c2],
            "watchlist_k_symbols": ["BNRG", "SBEV"],
            "focus_m": [],
            "focus_m_symbols": [],
            "universe_top_n": [{"symbol": "BNRG"}, {"symbol": "SBEV"}],
            "candidates": [c1, c2],
        }

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr(
        "src.strategy.strategy_runner._load_manual_focus_symbols",
        lambda: ["TMDE", "HURA"],
    )

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: ["TMDE", "HURA"]
        runner = orchestrator.strategy_runner._runner_registry["RossMomentumStrategyV1"]
        ross_strategy = runner.strategy

        def _run(context):
            symbols = [
                row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
                for row in context.get("watchlist", [])
            ]
            calls["process_watchlist"] = symbols
            ross_strategy.last_evaluated_symbols = [symbol for symbol in symbols if symbol]
            return {"trade_intents": [], "trade_ready_count": 0, "reports": []}

        runner.run = _run

        assert orchestrator.run_once() is True
        assert calls["process_watchlist"] == ["TMDE", "HURA"]
        output = capsys.readouterr().out
        assert "[FINAL_EVAL][MANUAL_ONLY] symbols=['TMDE', 'HURA'] reason=manual_override_only" in output
        assert "[MANUAL_FOCUS][HANDOFF] symbols=['TMDE', 'HURA'] source=MANUAL_FOCUS stock_selection_bypass=True setup_detection_required=True" in output
        assert "[ROSS][CONTRACT_VIOLATION]" not in output
        assert "[ROSS][CRITICAL] EMPTY_WATCHLIST_NO_TRADING_POSSIBLE" not in output
        assert "[ROSS][ERROR] EMPTY_SYMBOL_LIST" not in output
    finally:
        set_config_overrides(None)


def test_runtime_pipeline_manual_focus_off_hours_stays_prep_only(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "AH",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        }
    )

    def _scanner_cycle(**kwargs):
        c1 = replace(_candidate("BNRG", 10.0), session_label="AH", session_phase="AH")
        return {
            "candidate_metrics": [c1],
            "watchlist_k": [c1],
            "watchlist_k_symbols": ["BNRG"],
            "focus_m": [],
            "focus_m_symbols": [],
            "universe_top_n": [{"symbol": "BNRG"}],
            "candidates": [c1],
        }

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_: (lambda observations, _policy: observations))
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)
    monkeypatch.setattr(
        "src.strategy.strategy_runner._load_manual_focus_symbols",
        lambda: ["TMDE"],
    )

    try:
        orchestrator = CoreOrchestrator()
        orchestrator.market_data_snapshot_manager = SimpleNamespace(
            batch_snapshots=lambda symbols: ({}, [])
        )
        orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: ["TMDE"]
        runner = orchestrator.strategy_runner._runner_registry["RossMomentumStrategyV1"]

        def _run(_context):
            raise AssertionError("Ross runner should not execute during prep-only manual focus rejection")

        runner.run = _run

        assert orchestrator.run_once() is True
        output = capsys.readouterr().out
        assert "[MANUAL_FOCUS][PREP_ONLY] symbol=TMDE session=AH reason=MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED" in output
        assert "[ROSS][MANUAL_FOCUS_NO_SETUP] symbol=TMDE reason=MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED" in output
        assert "[ROSS][CONTRACT_VIOLATION]" not in output
        assert "[ROSS][CRITICAL] EMPTY_WATCHLIST_NO_TRADING_POSSIBLE" not in output
        assert "[ROSS][ERROR] EMPTY_SYMBOL_LIST" not in output
    finally:
        set_config_overrides(None)
