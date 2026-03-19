from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.config.runtime_config import EventReplayMode, RunMode
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.core.orchestrator import CoreOrchestrator, RuntimeSafetyError


@dataclass(frozen=True)
class _ResolvedRuntime:
    resolved_mode: RunMode
    allow_orders: bool
    event_replay_mode: EventReplayMode = EventReplayMode.OFF
    max_shares_per_order: int | None = None
    is_live_like: bool = True

    def describe(self) -> str:
        return (
            f"mode={self.resolved_mode.value} live_like={self.is_live_like} "
            f"allow_orders={self.allow_orders} max_shares_per_order={self.max_shares_per_order} "
            f"event_replay={self.event_replay_mode.value}"
        )


class _DummyLiveBroker:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


@pytest.fixture
def live_market_data_stubs(monkeypatch):
    monkeypatch.setattr(
        RuntimeModeManager,
        "resolve",
        classmethod(lambda cls: _ResolvedRuntime(resolved_mode=RunMode.LIVE, allow_orders=False)),
    )
    monkeypatch.setattr("src.core.orchestrator.IbkrLiveBroker", _DummyLiveBroker)
    monkeypatch.setattr("src.core.orchestrator.MarketDataHub", lambda *args, **kwargs: object())
    monkeypatch.setattr("src.core.orchestrator.MarketDataPriceFeed", lambda *args, **kwargs: object())


def test_live_readonly_does_not_require_order_submission(monkeypatch, live_market_data_stubs, capsys):
    monkeypatch.setattr(
        RuntimeModeManager,
        "resolve",
        classmethod(lambda cls: _ResolvedRuntime(resolved_mode=RunMode.LIVE, allow_orders=False)),
    )

    config = {
        "IBKR_API_WRITE_ALLOWED": False,
        "IBKR_ORDER_SUBMISSION_ENABLED": False,
        "IBKR_ORDER_TRANSLATION_ENABLED": False,
    }
    from src.core import orchestrator as orchestrator_module

    original_get_config = orchestrator_module.get_config
    monkeypatch.setattr(
        orchestrator_module,
        "get_config",
        lambda key: {
            "IBKR_API_WRITE_ALLOWED": config["IBKR_API_WRITE_ALLOWED"],
            "SELECTED_STRATEGY": "",
            "IBKR_MAX_SYMBOLS_PER_CYCLE": 10,
            "IBKR_LIVE_PORT": 7496,
            "IBKR_READONLY_ENABLED": False,
            "IBKR_KILL_SWITCH": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": config["IBKR_ORDER_SUBMISSION_ENABLED"],
            "IBKR_ORDER_TRANSLATION_ENABLED": config["IBKR_ORDER_TRANSLATION_ENABLED"],
        }.get(key, original_get_config(key)),
    )

    CoreOrchestrator()

    captured = capsys.readouterr()
    assert "[MODE] LIVE_READ_ONLY active — execution disabled" in captured.out


def test_execution_requires_order_submission(monkeypatch, live_market_data_stubs):
    monkeypatch.setattr(
        RuntimeModeManager,
        "resolve",
        classmethod(lambda cls: _ResolvedRuntime(resolved_mode=RunMode.LIVE, allow_orders=True)),
    )
    from src.core import orchestrator as orchestrator_module

    original_get_config = orchestrator_module.get_config
    monkeypatch.setattr(
        orchestrator_module,
        "get_config",
        lambda key: {
            "IBKR_API_WRITE_ALLOWED": True,
            "SELECTED_STRATEGY": "",
            "IBKR_MAX_SYMBOLS_PER_CYCLE": 10,
            "IBKR_LIVE_PORT": 7496,
            "IBKR_READONLY_ENABLED": False,
            "IBKR_KILL_SWITCH": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": False,
            "IBKR_ORDER_TRANSLATION_ENABLED": True,
        }.get(key, original_get_config(key)),
    )

    with pytest.raises(
        RuntimeSafetyError,
        match="Execution enabled but IBKR_ORDER_SUBMISSION_ENABLED=false.",
    ):
        CoreOrchestrator()
