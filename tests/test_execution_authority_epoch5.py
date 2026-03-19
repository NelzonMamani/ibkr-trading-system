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
from core.stop_controller import StopController
from execution.execution_engine import ExecutionEngine
from models.data_models import RiskDecision
from sim.price_feed import DeterministicPriceFeed


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def _risk_decision() -> RiskDecision:
    return RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="test",
        trader_type="MANUAL",
        strategy_name="TEST",
        direction="LONG",
        decision_id="decision-aapl",
    )


def test_execution_engine_blocks_read_only() -> None:
    set_config_overrides({"RUN_MODE": "READ_ONLY"})
    engine = ExecutionEngine(
        provider=None,
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        stop_controller=StopController(),
    )

    result = engine.execute_trade(_risk_decision())
    assert result.status == "BLOCKED"
    assert result.rationale == "LIVE_READ_ONLY_BLOCK"
    assert result.attempted is False


def test_execution_engine_uses_paper_provider_by_default() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    engine = ExecutionEngine(
        provider=None,
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        stop_controller=StopController(),
    )

    assert engine.provider is not None
    assert engine.provider.name() == "PAPER_EXECUTION_PROVIDER"
    assert engine.provider.is_live() is False
