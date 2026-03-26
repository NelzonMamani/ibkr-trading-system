from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.scanner import scanner_runner
from src.scanner.scanner_contract import ScannerRequest
from src.scanner.providers.mock_provider import MockScannerProvider
from src.scanner.session_pct_change import (
    compute_phase_aware_rvol,
    compute_session_aligned_pct_change,
    resolve_market_session_context,
    resolve_session_diagnostics,
)
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy

NY_TZ = ZoneInfo("America/New_York")


class _NoopFloatWorker:
    def enqueue(self, symbol: str) -> bool:
        return False


@pytest.fixture(autouse=True)
def _reset_runtime_state(monkeypatch):
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({"RUN_MODE": "PAPER", "RUN_MODE_EFFECTIVE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda *_args, **_kwargs: _NoopFloatWorker())
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})


def _premarket_utc(hour: int = 7, minute: int = 30) -> datetime:
    return datetime(2026, 3, 19, hour, minute, tzinfo=NY_TZ).astimezone(timezone.utc)


def _relaxed_policy():
    base = RossMomentumPolicy().stock_selection
    return replace(
        base,
        watchlist_limit_k=5,
        top_gainers_n=10,
        max_symbols_per_cycle=10,
        min_volume=0,
        min_premarket_volume=0,
        gap_min_pct=-99.0,
        watchlist_rvol_min=0.0,
        focus_rvol_min=0.0,
        require_catalyst=False,
        float_max_millions=100_000.0,
        session_allowlist=("PRE", "RTH", "AH", "OVN", "CLOSED", "WEEKEND"),
    )


def test_pre_session_not_overridden(monkeypatch, capsys):
    now_utc = _premarket_utc()
    monkeypatch.setattr(scanner_runner, "_utc_now", lambda: now_utc)

    diagnostics = resolve_session_diagnostics(now_utc)
    assert diagnostics.resolved_session == "PRE"
    assert diagnostics.canonical_session == "PRE"

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=_relaxed_policy(),
        provider=MockScannerProvider(),
        forced_session_label="PRE",
        forced_session_source="TEST_OVERRIDE",
    )

    assert payload["diagnostics"]["session_phase"] == "PRE"
    assert all(metric.session_label == "PRE" for metric in payload["candidate_metrics"])

    out = capsys.readouterr().out
    assert "[SESSION][MODE]" in out
    assert "resolved=PRE" in out
    assert "[ROSS][STATE] reset trading_day=2026-03-19 session=PRE" in out
    assert "session=WEEKEND" not in out
    assert "session=CLOSED" not in out


def test_no_weekend_override_during_pre():
    now_utc = _premarket_utc()
    session_context = resolve_market_session_context(
        now_utc,
        override_phase="PRE",
        override_source="TEST_OVERRIDE",
    )
    assert session_context.phase == "PRE"
    assert session_context.coarse == "PRE"
    assert session_context.source == "CONTEXT_OVERRIDE"

    pct_payload = compute_session_aligned_pct_change(
        session_label=session_context.phase,
        cur_last=12.0,
        ref_close_rth=10.0,
        rth_open_price=11.0,
        rth_close_price=10.0,
        ibkr_change_pct=20.0,
        persisted_pct_change=19.0,
    )
    rvol_payload = compute_phase_aware_rvol(
        session_label=session_context.phase,
        session_volume=250_000,
        avg_volume_20d=1_000_000,
    )

    assert pct_payload.session_label == "PRE"
    assert pct_payload.reference_label == "LAST_RTH_CLOSE"
    assert pct_payload.pct_source == "CALC(SESSION_REF)"
    assert rvol_payload.session_label == "PRE"
    assert rvol_payload.rvol_phase is not None
    assert "WEEKEND" not in {pct_payload.session_label, rvol_payload.session_label}


def test_preparation_mode_preserves_pre_session(monkeypatch):
    set_config_overrides({"RUN_MODE": "LIVE", "RUN_MODE_EFFECTIVE": "LIVE", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    captured: dict[str, str] = {}

    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.run_mode = RunMode.PAPER
    orchestrator.primary_strategy_key = "ross_momentum"
    orchestrator.event_collector = None
    orchestrator.connection_manager = SimpleNamespace(optional_client=None)
    orchestrator._build_scanner_policy_for_strategy = lambda strategy_key, session: (strategy_key, _relaxed_policy())
    orchestrator._build_scanner_request = lambda policy, strategy_name, session_phase: ScannerRequest(
        strategy_name=strategy_name,
        policy_name="ROSS_MOMENTUM",
        ranking_intent="ROSS_MOMENTUM_STOCK_SELECTION",
        session_phase=session_phase,
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        requested_top_n=25,
        instrument="STK",
        location_code="STK.US.MAJOR",
    )

    monkeypatch.setattr("src.core.orchestrator.resolve_market_session_context", lambda now=None: resolve_market_session_context(_premarket_utc()))

    def _run_scanner_cycle(**kwargs):
        captured["forced_session_label"] = kwargs["forced_session_label"]
        captured["forced_session_source"] = kwargs["forced_session_source"]
        return {"symbols": ["AAPL"], "watchlist_k": ["AAPL"]}

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _run_scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.write_premarket_prep_artifact", lambda **kwargs: captured.update({"artifact_session": kwargs["session"]}))

    CoreOrchestrator.run_preparation_mode(orchestrator)

    assert captured["forced_session_label"] == "PRE"
    assert captured["forced_session_source"] == "PREPARATION_MODE_ACTIVE"
    assert captured["artifact_session"] == "PRE"


def test_scanner_pipeline_pre_consistency(monkeypatch):
    now_utc = _premarket_utc()
    monkeypatch.setattr(scanner_runner, "_utc_now", lambda: now_utc)

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=_relaxed_policy(),
        provider=MockScannerProvider(),
        forced_session_label="PRE",
        forced_session_source="TEST_OVERRIDE",
    )

    assert payload["diagnostics"]["session_phase"] == "PRE"
    assert payload["watchlist_count"] > 0

    first_metric = payload["candidate_metrics"][0]
    assert first_metric.session_label == "PRE"
    assert first_metric.pct_source == "CALC(SESSION_REF)"
    assert first_metric.reference_label == "LAST_RTH_CLOSE"
    assert first_metric.rvol_phase is not None
    assert first_metric.rvol is not None
