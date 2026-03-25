from types import SimpleNamespace

from src.core.orchestrator import CoreOrchestrator


def _orchestrator() -> CoreOrchestrator:
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator._manual_focus_enabled = True
    return orchestrator


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

    assert _symbols(merged) == ["TMDE", "BNRG"]


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

    assert "OCGN" not in _symbols(merged)


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
