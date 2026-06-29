from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


_RUNNER_TEST_OVERRIDES = {
    "RUN_MODE": "READ_ONLY",
    "EXECUTION_ENABLED": False,
    "LIVE_EXECUTION_PROBE_MODE": False,
    "FORCE_EXECUTION_ON_TRADE_READY": False,
    "FORCE_RISK_APPROVAL_FOR_TRADE_READY": False,
    "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
    "SCANNER_DATA_SOURCE": "",
    "SELECTED_STRATEGY": "ross_momentum",
    "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
}


def _orchestrator() -> CoreOrchestrator:
    return CoreOrchestrator.__new__(CoreOrchestrator)


def _runner() -> StrategyRunner:
    return StrategyRunner(strategies=[RossMomentumStrategyV1()])


def _symbols(rows: list[object]) -> list[str]:
    return [getattr(row, "symbol", "") for row in rows]


def test_manual_focus_only_path() -> None:
    orchestrator = _orchestrator()
    manual_rows, rejected = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=["TMDE", "HURA", "CYN", "OCGN"],
        session_phase="PRE",
    )

    merged = orchestrator._merge_focus_candidates(
        scanner_focus=[],
        manual_candidates=manual_rows,
        session_phase="PRE",
    )

    assert rejected == []
    assert _symbols(merged) == ["TMDE", "HURA", "CYN", "OCGN"]


def test_auto_plus_manual_union() -> None:
    orchestrator = _orchestrator()
    auto_focus = [SimpleNamespace(symbol="TMDE"), SimpleNamespace(symbol="BNRG")]
    manual_rows, _ = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=["TMDE", "OCGN"],
        session_phase="PRE",
    )

    merged = orchestrator._merge_focus_candidates(
        scanner_focus=auto_focus,
        manual_candidates=manual_rows,
        session_phase="PRE",
    )

    assert _symbols(merged) == ["TMDE", "BNRG", "OCGN"]


def test_manual_focus_disabled() -> None:
    orchestrator = _orchestrator()

    merged = orchestrator._merge_focus_candidates(
        scanner_focus=[SimpleNamespace(symbol="TMDE")],
        manual_candidates=[],
        session_phase="PRE",
    )

    assert _symbols(merged) == ["TMDE"]


def test_manual_focus_invalid_symbol_rejected() -> None:
    orchestrator = _orchestrator()

    manual_rows, rejected = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=["TMDE", "$$$"],
        session_phase="PRE",
    )

    assert _symbols(manual_rows) == ["TMDE"]
    assert rejected == [("$$$", "INVALID_SYMBOL_FORMAT")]


def test_manual_focus_bypasses_watchlist() -> None:
    orchestrator = _orchestrator()
    auto_focus = [SimpleNamespace(symbol="BNRG")]
    manual_rows, _ = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=["OCGN"],
        session_phase="PRE",
    )

    merged = orchestrator._merge_focus_candidates(
        scanner_focus=auto_focus,
        manual_candidates=manual_rows,
        session_phase="PRE",
    )

    assert "OCGN" in _symbols(merged)


def test_manual_focus_with_empty_scanner_focus_runtime_regression() -> None:
    orchestrator = _orchestrator()
    watchlist_k = ["BNRG", "SBEV"]
    manual_rows, _ = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=["TMDE", "HURA"],
        session_phase="PRE",
    )

    final_eval = orchestrator._merge_focus_candidates(
        scanner_focus=[],
        manual_candidates=manual_rows,
        session_phase="PRE",
    )

    assert watchlist_k
    assert _symbols(final_eval) == ["TMDE", "HURA"]


def test_manual_focus_runner_logs_handoff_for_real_manual_rows(monkeypatch, capsys) -> None:
    set_config_overrides(dict(_RUNNER_TEST_OVERRIDES))
    monkeypatch.setenv("FORCE_EXECUTION_WINDOW", "false")
    try:
        orchestrator = _orchestrator()
        manual_rows, _ = orchestrator._resolve_manual_focus_candidates(
            manual_symbols=["TMDE", "HURA"],
            session_phase="PRE",
        )
        runner = _runner()
        backend = runner._runner_registry["RossMomentumStrategyV1"]
        calls: dict[str, object] = {}

        def _run(context):
            calls["rows"] = list(context["watchlist"])
            return {"trade_intents": [], "trade_ready_count": 0, "reports": []}

        backend.run = _run

        result = runner.process(
            strategy_key="ross_momentum",
            watchlist=manual_rows,
            snapshots={},
            session_label="PRE",
            timestamp_utc="2026-06-29T08:00:00+00:00",
            mode=SimpleNamespace(value="READ_ONLY"),
            session_phase="PRE",
            execution_allowed=True,
            execution_ready=True,
            prep_only=False,
        )

        assert result == []
        assert _symbols(list(calls["rows"])) == ["TMDE", "HURA"]
        output = capsys.readouterr().out
        assert "[MANUAL_FOCUS][HANDOFF] symbols=['TMDE', 'HURA'] source=MANUAL_FOCUS stock_selection_bypass=True setup_detection_required=True" in output
        assert "[ROSS][EVALUATION_SOURCE] symbol=TMDE source=MANUAL_FOCUS path=USER_SELECTED_TO_SETUP_EVAL" in output
        assert "[ROSS][EVALUATION_SOURCE] symbol=HURA source=MANUAL_FOCUS path=USER_SELECTED_TO_SETUP_EVAL" in output
    finally:
        set_config_overrides(None)


def test_manual_focus_runner_keeps_off_hours_prep_only(monkeypatch, capsys) -> None:
    set_config_overrides(dict(_RUNNER_TEST_OVERRIDES))
    monkeypatch.setenv("FORCE_EXECUTION_WINDOW", "false")
    try:
        orchestrator = _orchestrator()
        manual_rows, _ = orchestrator._resolve_manual_focus_candidates(
            manual_symbols=["TMDE"],
            session_phase="AH",
        )
        runner = _runner()
        backend = runner._runner_registry["RossMomentumStrategyV1"]
        ross_strategy = next(
            strategy
            for strategy in runner.strategies
            if getattr(strategy, "name", "") == "RossMomentumStrategyV1"
        )

        def _run(_context):
            raise AssertionError("Ross runner should not execute for off-hours manual-focus prep-only")

        backend.run = _run

        result = runner.process(
            strategy_key="ross_momentum",
            watchlist=manual_rows,
            snapshots={},
            session_label="AH",
            timestamp_utc="2026-06-29T22:00:00+00:00",
            mode=SimpleNamespace(value="READ_ONLY"),
            session_phase="AH",
            execution_allowed=False,
            execution_ready=False,
            prep_only=True,
        )

        assert result == []
        assert ross_strategy.last_evaluated_symbols == ["TMDE"]
        output = capsys.readouterr().out
        assert "[MANUAL_FOCUS][PREP_ONLY] symbol=TMDE session=AH reason=MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED" in output
        assert "[ROSS][MANUAL_FOCUS_NO_SETUP] symbol=TMDE reason=MARKET_NOT_EXECUTABLE_BUT_USER_WATCH_ACCEPTED" in output
    finally:
        set_config_overrides(None)
