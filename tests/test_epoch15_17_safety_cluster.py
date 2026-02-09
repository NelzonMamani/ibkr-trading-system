import pytest

from src.config.runtime_config import RunMode
from src.core.faults import FaultCategory, classify_exception, decide_recovery_action, fault_policy_snapshot
from src.risk.no_trade_contexts import evaluate_no_trade_contexts
from src.models.risk_decision import (
    BROKER_READONLY_BLOCK,
    CIRCUIT_BREAKER_TRIPPED,
    EXECUTION_DISABLED,
    LIVE_READ_ONLY_BLOCK,
    RISK_SESSION_BLOCK,
)
from src.strategy_portfolio.arbitration import ArbitrationInput, arbitrate_symbol
from src.strategy_portfolio.contracts import SignalIntent


def test_fault_policy_snapshot_covers_categories():
    snapshot = fault_policy_snapshot()
    for category in FaultCategory:
        assert category.value in snapshot
        assert "severity" in snapshot[category.value]
        assert "description" in snapshot[category.value]

    fault = classify_exception(RuntimeError("[SAFETY] stop"))
    action = decide_recovery_action(fault, RunMode.LIVE)
    assert action.name == "HALT_SYSTEM"


@pytest.mark.parametrize(
    ("run_mode", "expected_first"),
    [
        (RunMode.READ_ONLY, LIVE_READ_ONLY_BLOCK),
        (RunMode.LIVE, EXECUTION_DISABLED),
    ],
)
def test_no_trade_contexts_order(run_mode, expected_first):
    contexts = evaluate_no_trade_contexts(
        run_mode=run_mode,
        execution_enabled=False,
        session_blocked=True,
        broker_readonly=True,
        circuit_breaker_tripped=True,
        data_quality_block=False,
    )
    assert contexts[0].code == CIRCUIT_BREAKER_TRIPPED
    assert expected_first in [context.code for context in contexts]
    assert RISK_SESSION_BLOCK in [context.code for context in contexts]
    if run_mode == RunMode.LIVE:
        assert BROKER_READONLY_BLOCK in [context.code for context in contexts]


def test_arbitration_budget_blocks_strategy():
    inputs = [
        ArbitrationInput(
            symbol="AAPL",
            strategy_id="strategy_a",
            priority=1,
            proposed_intent=SignalIntent.ENTER_LONG,
        ),
        ArbitrationInput(
            symbol="AAPL",
            strategy_id="strategy_b",
            priority=5,
            proposed_intent=SignalIntent.ENTER_LONG,
        ),
    ]
    result = arbitrate_symbol(
        inputs,
        strategy_budget_map={"strategy_b": 0.0},
    )
    assert result.winner_strategy_id == "strategy_a"
    assert ("strategy_b", "allocation_exhausted") in result.denied
