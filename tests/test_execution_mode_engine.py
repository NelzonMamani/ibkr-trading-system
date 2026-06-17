import io
import sys
from types import SimpleNamespace

from src import main as main_module
from src.core.engines.execution_mode_engine import ExecutionModeEngine


def _intent(**kwargs):
    payload = {
        "strategy_name": "TEST_STRATEGY",
        "execution_refinement_mode": "NONE",
        "execution_block_reason": None,
    }
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def _context(**kwargs):
    payload = {
        "session": "PRE",
        "rvol": 3.0,
        "spread": 0.05,
    }
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def test_execution_mode_matrix_applied_by_session() -> None:
    engine = ExecutionModeEngine()

    cases = [
        ("PRE", "CONDITIONAL", "1m", "10s"),
        ("RTH_OPEN", "AGGRESSIVE", "1m", "10s"),
        ("RTH_MID", "NORMAL", "1m", "10s"),
        ("RTH_LATE", "STRUCTURAL", "5m", "1m"),
        ("AH", "LOW_LIQUIDITY", "5m", "1m"),
    ]

    for session, mode, primary, refinement in cases:
        intent = _intent()
        out = engine.apply(intent, _context(session=session))
        assert out.execution_mode == mode
        assert out.execution_primary_timeframe == primary
        assert out.execution_refinement_timeframe == refinement


def test_fallback_logic_preserved_for_incomplete_context(monkeypatch) -> None:
    original_stdout = sys.stdout
    bytes_buffer = io.BytesIO()
    cp1252_stream = io.TextIOWrapper(
        bytes_buffer,
        encoding="cp1252",
        errors="strict",
        write_through=True,
    )
    monkeypatch.setattr(sys, "stdout", cp1252_stream)
    main_module._configure_console_output()
    print("runtime -> safe", end="")
    print(" | unicode → safe", end="")
    cp1252_stream.flush()
    monkeypatch.setattr(sys, "stdout", original_stdout)

    assert bytes_buffer.getvalue().decode("cp1252") == "runtime -> safe | unicode ? safe"

    engine = ExecutionModeEngine()
    intent = _intent()

    out = engine.apply(intent, SimpleNamespace(session="RTH_OPEN", rvol=None, spread=0.04))

    assert out.execution_mode == "FALLBACK"
    assert out.execution_primary_timeframe == "1m"
    assert out.execution_refinement_timeframe == "10s"


def test_ross_execution_blocked_in_after_hours() -> None:
    engine = ExecutionModeEngine()
    intent = _intent(strategy_name="ROSS_MOMENTUM")

    out = engine.apply(intent, _context(session="AH"))

    assert out.execution_mode == "REJECTED"
    assert out.execution_block_reason == "ROSS_AH_BLOCKED"


def test_fast_micro_pullback_blocked_in_rth_late() -> None:
    engine = ExecutionModeEngine()
    intent = _intent(execution_refinement_mode="FAST_MICRO_PULLBACK")

    out = engine.apply(intent, _context(session="RTH_LATE"))

    assert out.execution_refinement_mode == "NONE"
    assert out.execution_block_reason == "FAST_MICRO_PULLBACK_BLOCKED_RTH_LATE"


def test_fast_micro_pullback_soft_downgrade_in_rth_mid() -> None:
    engine = ExecutionModeEngine()
    intent = _intent(execution_refinement_mode="FAST_MICRO_PULLBACK")

    out = engine.apply(intent, _context(session="RTH_MID", rvol=1.0, spread=0.2))

    assert out.execution_refinement_mode == "MICRO_PULLBACK"
    assert out.execution_block_reason == "FAST_MICRO_PULLBACK_DOWNGRADED_RTH_MID"
