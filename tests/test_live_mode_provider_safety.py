from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from config.runtime_config import RunMode
from scanner import scanner_runner
from scanner.providers.mock_provider import MockScannerProvider


@pytest.fixture(autouse=True)
def _reset_scanner_state():
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})


def test_live_mode_rejects_mock_provider(monkeypatch):
    monkeypatch.setattr(scanner_runner, "build_provider", lambda *args, **kwargs: MockScannerProvider())
    set_config_overrides({"RUN_MODE": RunMode.LIVE.value, "SCANNER_DATA_SOURCE": "IBKR"})

    with pytest.raises(RuntimeError, match="MOCK is not permitted"):
        scanner_runner.run_scanner_cycle(mode="integrated")


@pytest.mark.parametrize("mode", [RunMode.SIM.value, RunMode.PAPER.value])
def test_sim_mode_allows_mock_provider(monkeypatch, mode):
    monkeypatch.setattr(scanner_runner, "build_provider", lambda *args, **kwargs: MockScannerProvider())
    set_config_overrides({"RUN_MODE": mode, "SCANNER_DATA_SOURCE": "MOCK"})

    payload = scanner_runner.run_scanner_cycle(mode="integrated")

    assert payload.get("diagnostics", {}).get("provider_source") == "MOCK"
