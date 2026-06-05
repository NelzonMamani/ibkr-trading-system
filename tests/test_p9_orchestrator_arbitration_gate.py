from __future__ import annotations

from types import SimpleNamespace

from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.core.strategy_arbitration_authority import StrategyArbitrationAuthority
from src.models.data_models import TradeIntent


def _intent(
    strategy_name: str,
    symbol: str,
    *,
    priority: int,
    confidence: float = 0.8,
    direction: str = "LONG",
) -> TradeIntent:
    intent = TradeIntent(
        symbol=symbol,
        direction=direction,
        strategy_name=strategy_name,
        confidence=confidence,
        rationale="p9 orchestrator gate",
        trader_type="P9_TEST",
    )
    intent.priority = priority
    intent.quantity = 1
    intent.entry_price = 100.0
    return intent


def _orchestrator_shell(*, recovery_complete: bool = True, run_mode: RunMode = RunMode.LIVE) -> CoreOrchestrator:
    orchestrator = object.__new__(CoreOrchestrator)
    orchestrator.run_mode = run_mode
    orchestrator._current_cycle_id = "cycle-p9"
    orchestrator.execution_engine = SimpleNamespace(
        startup_recovery_complete=lambda: recovery_complete,
    )
    orchestrator.strategy_arbitration_authority = StrategyArbitrationAuthority()
    return orchestrator


def test_orchestrator_runs_p9_before_downstream_capital_gates() -> None:
    orchestrator = _orchestrator_shell()
    low = _intent("alpha", "AAPL", priority=1)
    high = _intent("beta", "AAPL", priority=5)

    selected, decision = orchestrator._apply_p9_strategy_arbitration([low, high])

    assert [intent.strategy_name for intent in selected] == ["beta"]
    assert decision.selected_intent_ids == [high.intent_id]
    assert decision.reasons[low.intent_id] == "DUPLICATE_SYMBOL"


def test_orchestrator_p9_blocks_when_recovery_incomplete() -> None:
    orchestrator = _orchestrator_shell(recovery_complete=False)
    intent = _intent("alpha", "AAPL", priority=1)

    selected, decision = orchestrator._apply_p9_strategy_arbitration([intent])

    assert selected == []
    assert decision.reasons[intent.intent_id] == "RECOVERY_NOT_COMPLETE"


def test_orchestrator_p9_read_only_reports_without_executable_selection() -> None:
    orchestrator = _orchestrator_shell(run_mode=RunMode.READ_ONLY)
    intent = _intent("alpha", "AAPL", priority=1)

    selected, decision = orchestrator._apply_p9_strategy_arbitration([intent])

    assert selected == []
    assert decision.reasons[intent.intent_id] == "READ_ONLY_BLOCKED"
