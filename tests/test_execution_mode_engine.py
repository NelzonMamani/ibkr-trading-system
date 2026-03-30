from types import SimpleNamespace

from src.core.engines.execution_mode_engine import ExecutionModeEngine
from src.models.data_models import TradeIntent


def _intent(refinement: str = "FAST_MICRO_PULLBACK") -> TradeIntent:
    return TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="test",
        confidence=0.9,
        rationale="test",
        execution_refinement_mode=refinement,
    )


def test_premarket_rejects_low_rvol() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="PRE", rvol=1.4, spread=0.01)
    assert engine.apply(_intent(), context) is None


def test_premarket_rejects_wide_spread() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="PRE", rvol=1.8, spread=0.03)
    assert engine.apply(_intent(), context) is None


def test_after_hours_rejects_all_micro_pullback() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="AH", rvol=5.0, spread=0.01)
    assert engine.apply(_intent(), context) is None


def test_rth_open_allows_fast() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="RTH_OPEN", rvol=2.0, spread=0.01)
    out = engine.apply(_intent("FAST_MICRO_PULLBACK"), context)
    assert out is not None
    assert out.execution_refinement_mode == "FAST_MICRO_PULLBACK"
    assert out.execution_primary_timeframe == "1m"
    assert out.execution_refinement_timeframe == "10s"
    assert out.execution_mode == "HIGH_SPEED"


def test_rth_mid_downgrades_fast_to_slow() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="RTH_MID", rvol=2.0, spread=0.01)
    out = engine.apply(_intent("FAST_MICRO_PULLBACK"), context)
    assert out is not None
    assert out.execution_refinement_mode == "SLOW_MICRO_PULLBACK"
    assert out.execution_refinement_timeframe == "1m"


def test_rth_late_blocks_execution_refinement() -> None:
    engine = ExecutionModeEngine()
    context = SimpleNamespace(session="RTH_LATE", rvol=2.0, spread=0.01)
    assert engine.apply(_intent("SLOW_MICRO_PULLBACK"), context) is None
