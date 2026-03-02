from src.core.orchestrator import CoreOrchestrator


class _DummyPolicy:
    pass


def _orchestrator_for_key(key: str) -> CoreOrchestrator:
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.selected_strategy_key = key
    return orchestrator


def test_active_policy_v2_enabled_path(monkeypatch) -> None:
    orchestrator = _orchestrator_for_key("ross_momentum")
    policy = _DummyPolicy()

    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda strategy_key: policy)
    monkeypatch.setattr("src.core.orchestrator.is_policy_v2_enabled_for_strategy", lambda strategy_key: True)

    assert orchestrator._active_policy_v2() is policy


def test_active_policy_v2_global_or_allowlist_disabled(monkeypatch) -> None:
    orchestrator = _orchestrator_for_key("ross_momentum")

    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda strategy_key: _DummyPolicy())
    monkeypatch.setattr("src.core.orchestrator.is_policy_v2_enabled_for_strategy", lambda strategy_key: False)

    assert orchestrator._active_policy_v2() is None


def test_active_policy_v2_missing_registry_entry(monkeypatch) -> None:
    orchestrator = _orchestrator_for_key("unknown")

    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda strategy_key: None)
    monkeypatch.setattr("src.core.orchestrator.is_policy_v2_enabled_for_strategy", lambda strategy_key: True)

    assert orchestrator._active_policy_v2() is None
