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
from src.execution.startup_recovery_authority import RecoveryState, StartupRecoveryResult
from config.runtime_config import RunMode
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


def _stub_startup_recovery_complete(orchestrator: CoreOrchestrator) -> None:
    orchestrator.execution_engine.startup_recovery_state = RecoveryState.RECOVERY_COMPLETE
    orchestrator.execution_engine.startup_recovery_result = StartupRecoveryResult(
        state=RecoveryState.RECOVERY_COMPLETE,
        reason="TEST_RECOVERY_COMPLETE",
    )
    orchestrator.execution_engine._failsafe_block_new_entries = False


@pytest.mark.parametrize(
    ("mode", "expected_connect_calls", "expected_log"),
    [
        ("SIM", 0, "[CONNECTIVITY][SKIP] run_mode=SIM forcing MOCK scanner provider."),
        ("PAPER", 1, "[CONNECTIVITY][PAPER] broker-connected validation path enabled"),
        ("LIVE", 1, "[CONNECTIVITY][LIVE] broker-connected production path enabled"),
    ],
)
def test_run_mode_connectivity_path_enforcement(
    monkeypatch,
    capsys,
    mode: str,
    expected_connect_calls: int,
    expected_log: str,
) -> None:
    set_config_overrides(
        {
            "RUN_MODE": mode,
            "RISK_PROFILE": "MICRO",
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
        }
    )

    orchestrator = CoreOrchestrator()
    if mode in {"PAPER", "LIVE"}:
        _stub_startup_recovery_complete(orchestrator)
    connect_calls = {"count": 0}

    def _record_connect():
        connect_calls["count"] += 1
        return None

    monkeypatch.setattr(orchestrator.connection_manager, "ensure_connected", _record_connect)
    should_continue = orchestrator.run_once()
    assert should_continue in {True, False}

    out = capsys.readouterr().out
    assert expected_log in out
    assert connect_calls["count"] == expected_connect_calls


def test_execution_engine_blocks_live_validation_override() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    engine = ExecutionEngine(
        provider=None,
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        stop_controller=StopController(),
    )
    engine.run_mode = RunMode.LIVE

    decision = RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="live override protection test",
        trader_type="MANUAL",
        strategy_name="TEST",
        direction="LONG",
        decision_id="decision-live-override-aapl",
    )
    decision.validation_override = True
    result = engine.execute_trade(decision)

    assert result.attempted is False
    assert result.status == "BLOCKED"
    assert result.rationale == "VALIDATION_OVERRIDE_LIVE_PROTECTION"
