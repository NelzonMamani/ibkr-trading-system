from __future__ import annotations

import asyncio
import pytest


@pytest.fixture(autouse=True)
def _force_test_execution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_ENV", "TEST")


@pytest.fixture(scope="session", autouse=True)
def _session_event_loop_bootstrap():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)
