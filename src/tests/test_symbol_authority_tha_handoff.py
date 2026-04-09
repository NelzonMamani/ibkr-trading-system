from __future__ import annotations

from pathlib import Path

from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def test_orchestrator_symbol_normalization_preserves_authority_order() -> None:
    symbols = CoreOrchestrator._normalize_symbols(["tmde", "HURA", "", "TMDE", "cyn", None, "CYN"])
    assert symbols == ["TMDE", "HURA", "CYN"]


def test_orchestrator_logs_symbol_authority_source_merge_drop_final() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert '_emit_symbol_authority(\n            "SOURCE"' in text
    assert '_emit_symbol_authority(\n                "MERGE"' in text
    assert "[SYMBOL_AUTHORITY][DROP]" in text
    assert '_emit_symbol_authority(\n            "FINAL"' in text


def test_orchestrator_uses_input_authority_log_for_ross_process() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert "[ROSS][INPUT_AUTHORITY]" in text
    assert "[ROSS][NO_SYMBOLS_REASON]" in text


def test_orchestrator_tha_blocks_entries_without_pre_strategy_symbol_erasure() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert "action=block_entries_only" in text
    assert "preserved_authority=True" in text
    assert "allowed_by_tha" not in text


def test_orchestrator_tha_force_flat_policy_log_is_explicit() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert "[THA][FLAT_POLICY]" in text
    assert "THA_OUTSIDE_WINDOW" in text


def test_orchestrator_tha_entry_policy_log_is_explicit() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert "[THA][ENTRY_POLICY]" in text
    assert "blocked_entries=" in text


def test_ross_strategy_logs_empty_watchlist_reason_truthfully(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    output = strategy.process_watchlist(
        watchlist=[],
        snapshots={},
        session_label="PRE",
        timestamp_utc="2026-04-09T00:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="PRE",
    )
    captured = capsys.readouterr().out
    assert output == []
    assert "[ROSS][CRITICAL] EMPTY_WATCHLIST_NO_TRADING_POSSIBLE" in captured
    assert "[ROSS][NO_SYMBOLS_REASON]" in captured


def test_ross_strategy_logs_input_authority_for_non_empty_watchlist(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    strategy.process_watchlist(
        watchlist=[{"symbol": "OCGN", "volume": 200_000}],
        snapshots={},
        session_label="PRE",
        timestamp_utc="2026-04-09T00:00:01+00:00",
        mode=RunMode.PAPER,
        session_phase="PRE",
    )
    captured = capsys.readouterr().out
    assert "[ROSS][INPUT_AUTHORITY]" in captured
    assert "watchlist_symbols=1" in captured
