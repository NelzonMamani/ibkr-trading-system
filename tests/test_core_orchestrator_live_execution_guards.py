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


def test_live_execution_disabled_is_runtime_fatal(monkeypatch, live_market_data_stubs):
    monkeypatch.setattr(
        RuntimeModeManager,
        "resolve",
        classmethod(lambda cls: _ResolvedRuntime(resolved_mode=RunMode.LIVE, allow_orders=False)),
    )

    from src.core import orchestrator as orchestrator_module

    validator = getattr(orchestrator_module, "validate_live_execution_invariant", None)
    if validator is None:  # pragma: no cover - compatibility with pre-PR534 behavior
        orchestrator = CoreOrchestrator()
        assert orchestrator.execution_enabled is False
        return

    with pytest.raises(RuntimeError, match="LIVE execution disabled"):
        validator(run_mode=RunMode.LIVE, execution_enabled=False)


def test_execution_ignores_raw_submission_flag_when_runtime_allows_orders(monkeypatch, live_market_data_stubs):
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
    monkeypatch.setattr(orchestrator_module, "get_ibkr_order_translation_enabled", lambda: True)
    monkeypatch.setattr(orchestrator_module, "get_ibkr_api_write_allowed", lambda: True)
    monkeypatch.setattr(orchestrator_module, "get_ibkr_readonly_enabled", lambda: False)
    monkeypatch.setattr(orchestrator_module, "get_ibkr_order_submission_enabled", lambda: True)

    CoreOrchestrator()
