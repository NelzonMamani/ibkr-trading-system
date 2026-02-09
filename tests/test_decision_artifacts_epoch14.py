from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from core.intent import build_decision_artifact
from execution.execution_engine import ExecutionEngine
from models.data_models import RiskDecision, TradeIntent
from models.risk_decision import DECISION_ARTIFACT_MISSING
from risk.risk_engine import RiskEngine


@pytest.fixture(autouse=True)
def _reset_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def _make_intent(symbol: str, confidence: float) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        direction="LONG",
        strategy_name="UnitTestStrategy",
        confidence=confidence,
        rationale="unit-test",
        trader_type="MOMENTUM",
        stop_loss_price=9.5,
    )


def test_decision_artifact_determinism():
    intents = [_make_intent("AAA", 0.7), _make_intent("BBB", 0.8)]
    artifact_a = build_decision_artifact(
        strategy_name="UnitTestStrategy",
        run_mode="PAPER",
        session_phase="REGULAR",
        intents=intents,
        source="unit-test",
        created_at="2025-01-01T00:00:00Z",
        metadata={"tick": 1},
    )
    artifact_b = build_decision_artifact(
        strategy_name="UnitTestStrategy",
        run_mode="PAPER",
        session_phase="REGULAR",
        intents=list(reversed(intents)),
        source="unit-test",
        created_at="2025-01-01T00:00:00Z",
        metadata={"tick": 1},
    )

    assert artifact_a.decision_id == artifact_b.decision_id


def test_strategy_decision_execution_smoke():
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "RUN_MODE_EFFECTIVE": "PAPER",
            "EXECUTION_ENABLED": True,
            "EXECUTION_ENABLED_EFFECTIVE": True,
            "ACTIVE_SESSIONS": ["PRE", "REGULAR", "AFTER"],
        }
    )
    intent = _make_intent("XYZ", 0.9)
    artifact = build_decision_artifact(
        strategy_name="UnitTestStrategy",
        run_mode="PAPER",
        session_phase="REGULAR",
        intents=[intent],
        source="unit-test",
        created_at="2025-01-01T00:00:00Z",
        metadata={"tick": 5},
    )
    intent.decision_id = artifact.decision_id

    risk_engine = RiskEngine()
    decision = risk_engine.evaluate_trade_intent(intent)
    assert decision.decision_id == artifact.decision_id

    execution_engine = ExecutionEngine()
    execution_engine.current_tick = 5
    result = execution_engine.execute_trade(decision)
    assert result.rationale != DECISION_ARTIFACT_MISSING


def test_replay_safety_blocks_without_decision_artifact():
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "RUN_MODE_EFFECTIVE": "PAPER",
            "EXECUTION_ENABLED": True,
            "EXECUTION_ENABLED_EFFECTIVE": True,
        }
    )
    decision = RiskDecision(
        symbol="ABC",
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="unit-test",
        trader_type="MANUAL",
        strategy_name="UnitTestStrategy",
        direction="LONG",
    )
    execution_engine = ExecutionEngine()
    execution_engine.current_tick = 1
    result = execution_engine.execute_trade(decision)
    assert result.status == "BLOCKED"
    assert result.rationale == DECISION_ARTIFACT_MISSING
