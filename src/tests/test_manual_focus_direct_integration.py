from types import SimpleNamespace

from src.core.orchestrator import CoreOrchestrator
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _orchestrator() -> CoreOrchestrator:
    return CoreOrchestrator.__new__(CoreOrchestrator)


def _runner() -> StrategyRunner:
    return StrategyRunner(strategies=[RossMomentumStrategyV1()])


def _symbols(rows: list[object]) -> list[str]:
    values: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            values.append(str(row.get("symbol") or ""))
        else:
            values.append(getattr(row, "symbol", ""))
    return values


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


def test_manual_focus_runner_rehydrates_configured_symbols(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategy.strategy_runner._load_manual_focus_symbols",
        lambda: ["TMDE", "HURA"],
    )
    runner = _runner()
    runner.receive_watchlist_snapshot(
        watchlist_symbols=["TMDE", "HURA", "BNRG"],
        snapshots={},
        session_label="PRE",
        timestamp_utc="2026-06-29T08:00:00+00:00",
    )
    backend = runner._runner_registry["RossMomentumStrategyV1"]
    calls: dict[str, object] = {}

    def _run(context):
        calls["rows"] = list(context["watchlist"])
        return {"trade_intents": [], "trade_ready_count": 0, "reports": []}

    backend.run = _run

    result = runner.process(
        strategy_key="ross_momentum",
        watchlist=[],
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
    rows = list(calls["rows"])
    assert _symbols(rows) == ["TMDE", "HURA"]
    first = rows[0]
    assert isinstance(first, dict)
    assert first["watchlist_source"] == "MANUAL_FOCUS"
    assert first["selection_rationale"]["source"] == "MANUAL_FOCUS"
    assert first["selection_rationale"]["stock_selection_bypass"] is True
    assert first["selection_rationale"]["setup_detection_required"] is True
    assert first["gate_checks"]["stock_selection_bypass"] is True
    assert first["gate_checks"]["risk_required"] is True
    assert first["gate_checks"]["execution_required"] is True
    assert "USER_SELECTED_SYMBOL" in first["eligibility_reason_codes"]
    assert "MANUAL_BYPASS_RVOL_FILTER" in first["eligibility_reason_codes"]


def test_manual_focus_runner_keeps_off_hours_prep_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.strategy.strategy_runner._load_manual_focus_symbols",
        lambda: ["TMDE"],
    )
    runner = _runner()
    runner.receive_watchlist_snapshot(
        watchlist_symbols=["TMDE"],
        snapshots={},
        session_label="AH",
        timestamp_utc="2026-06-29T22:00:00+00:00",
    )
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
        watchlist=[],
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
