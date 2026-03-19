from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from core.active_trade_registry import ActiveTradeRegistry
from core.event_collector import EventCollector
from core.orchestrator import CoreOrchestrator
from core.stop_controller import StopController
from execution.execution_engine import ExecutionEngine
from models.data_models import RiskDecision
from sim.price_feed import DeterministicPriceFeed


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def test_execution_engine_clamps_micro_risk_profile_to_one_share(capsys) -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True, "RISK_PROFILE": "MICRO"})
    engine = ExecutionEngine(
        provider=None,
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        stop_controller=StopController(),
    )

    engine.current_tick = 1
    decision = RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=25,
        risk_level="LOW",
        rationale="micro clamp test",
        trader_type="MANUAL",
        strategy_name="TEST",
        direction="LONG",
        decision_id="decision-micro-aapl",
    )
    result = engine.execute_trade(decision)

    assert result.requested_quantity == 1
    out = capsys.readouterr().out
    assert "[RISK][MICRO_CLAMP]" in out


def test_paper_run_once_skips_ibkr_connectivity(monkeypatch) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "RISK_PROFILE": "MICRO",
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
        }
    )

    def _unexpected_connect(self):
        raise AssertionError("PAPER mode should not call ensure_connected")

    monkeypatch.setattr(
        "core.managers.connection_manager.ConnectionManager.ensure_connected",
        _unexpected_connect,
    )

    orchestrator = CoreOrchestrator()
    should_continue = orchestrator.run_once()
    assert should_continue in {True, False}
