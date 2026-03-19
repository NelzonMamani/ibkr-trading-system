from src.config.config_resolver import set_config_overrides
from src.core_engine.orchestrator import run_cycles
from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.core_engine.health import HealthStatus
from src.risk.risk_audit import evaluate_trade_intents
import pytest


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def test_orchestrator_readonly_cycle():
    set_config_overrides({"SCANNER_DATA_SOURCE": "MOCK", "RUN_MODE": "READ_ONLY"})
    summaries = run_cycles(mode="READONLY", cycles=1)
    summary = summaries[0]
    assert summary.stage_order == [
        "Scanner",
        "Data",
        "Patterns",
        "Strategy",
        "Risk",
        "Execution",
        "Storage",
        "Health",
    ]
    for event in summary.execution_events:
        assert event.action != "SUBMITTED"


def test_risk_blocks_on_critical():
    intents = [
        TradeIntentRecord(
            symbol="TEST",
            intent_id="TEST-1",
            setup_id="Micro Pullback",
            side="LONG",
            entry="Breakout",
            stop="Below support",
            rationale="Test intent",
            tags=[],
        )
    ]
    decisions = evaluate_trade_intents(
        intents=intents,
        mode=RunMode.LIVE,
        health_status=HealthStatus.CRITICAL,
    )
    assert decisions[0].decision == "BLOCK"
