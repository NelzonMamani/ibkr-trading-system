from src.core_engine.orchestrator import run_cycles
from src.core_engine.events import TradeIntentRecord
from src.core_engine.state import RunMode
from src.core_engine.health import HealthStatus
from src.risk.risk_audit import evaluate_trade_intents


def test_orchestrator_readonly_cycle():
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
        mode=RunMode.LIVE_1SHARE,
        health_status=HealthStatus.CRITICAL,
    )
    assert decisions[0].decision == "BLOCK"
