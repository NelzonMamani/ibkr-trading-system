from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as pr1040
from src.config.config_resolver import set_config_overrides
from src.data.float_discovery_worker import FloatDiscoveryResult
from src.scanner import scanner_runner
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import scanner_request_from_policy
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


class _ControlledRuntimeProvider:
    source_name = "IBKR"

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(row["symbol"]).upper(): row for row in rows}
        self._symbols = [str(row["symbol"]).upper() for row in rows]
        self.last_scan_details = {
            "selected_location_code": "STK.US.MAJOR",
            "selected_scan_code": "TOP_PERC_GAIN",
            "returned_rows": len(self._symbols),
            "retry_attempts": 0,
            "retry_exhausted": False,
            "symbol_details": {
                symbol: {
                    "conId": 900_000 + idx,
                    "secType": "STK",
                    "exchange": "SMART",
                    "primaryExchange": "NASDAQ",
                    "tradingClass": symbol,
                    "localSymbol": symbol,
                    "currency": "USD",
                }
                for idx, symbol in enumerate(self._symbols, start=1)
            },
        }

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        return self._symbols[:limit]

    def get_quote(self, symbol: str) -> QuoteData:
        row = self._rows[symbol.upper()]
        last = float(row.get("last", 7.0))
        prev_close = float(row.get("prev_close", 5.0))
        bid = row.get("bid", round(last - 0.01, 2))
        ask = row.get("ask", round(last + 0.01, 2))
        pct_change = round(((last - prev_close) / prev_close) * 100.0, 2)
        return QuoteData(
            symbol=symbol,
            bid=None if bid is None else float(bid),
            ask=None if ask is None else float(ask),
            last=last,
            vwap=last,
            open=prev_close,
            high=round(last * 1.05, 2),
            low=round(last * 0.95, 2),
            close=prev_close,
            change_percent=pct_change,
            volume=float(row.get("volume", 1_600_000)),
            timestamp_utc=None,
            data_quality_flags=tuple(row.get("data_quality_flags", ()) or ()),
        )

    def get_prev_close(self, symbol: str) -> float:
        return float(self._rows[str(symbol).upper()].get("prev_close", 5.0))

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        row = self._rows[symbol.upper()]
        volume = int(row.get("volume", 1_600_000))
        avg_volume = int(row.get("avg_volume", 200_000))
        rvol = round(volume / avg_volume, 2) if avg_volume else None
        return IntradayStats(
            current_intraday_volume=volume,
            current_volume_source_label="PR1050_TEST",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=rvol,
            relative_volume_category="HIGH" if rvol and rvol >= 3.0 else "NORMAL",
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="PR1050_TEST",
        )

    def get_float(self, symbol: str) -> int | None:
        value = self._rows[symbol.upper()].get("float_shares")
        return None if value is None else int(value)

    def get_previous_rth_close(self, identity) -> float:
        symbol = str(getattr(identity, "symbol", identity)).upper()
        return self.get_prev_close(symbol)

    def get_average_daily_volume(self, identity, window: int) -> tuple[int, int]:
        symbol = str(getattr(identity, "symbol", identity)).upper()
        return int(self._rows[symbol].get("avg_volume", 200_000)), min(window, 20)

    def get_daily_bars(self, identity, lookback_days: int, **kwargs):
        symbol = str(getattr(identity, "symbol", identity)).upper()
        prev_close = self.get_prev_close(symbol)
        avg_volume, window = self.get_average_daily_volume(symbol, lookback_days)
        return [
            SimpleNamespace(date=f"2026-01-{idx + 1:02d}", close=prev_close, volume=avg_volume)
            for idx in range(window)
        ]


class _DiscoveryWorkerStub:
    def __init__(self, values: dict[str, int | None]) -> None:
        self.values = {symbol.upper(): value for symbol, value in values.items()}
        self.queued: list[str] = []
        self.requests: list[str] = []

    def enqueue(self, symbol: str) -> bool:
        normalized = symbol.upper()
        if normalized in self.queued:
            return False
        self.queued.append(normalized)
        return True

    def discover_now(self, symbol: str) -> FloatDiscoveryResult:
        normalized = symbol.upper()
        self.requests.append(normalized)
        value = self.values.get(normalized)
        return FloatDiscoveryResult(
            symbol=normalized,
            value=value,
            source="PR1050_TEST" if value else "UNKNOWN",
            cache_used=False,
            fallback_used=False,
            failures=() if value else (("PR1050_TEST", "not_found"),),
        )


class _BackgroundCacheWriteWorkerStub:
    def __init__(self, cache_file: Path, values: dict[str, int | None]) -> None:
        self.cache_file = cache_file
        self.values = {symbol.upper(): value for symbol, value in values.items()}
        self.queued: list[str] = []
        self.requests: list[str] = []

    def enqueue(self, symbol: str) -> bool:
        normalized = symbol.upper()
        if normalized in self.queued:
            return False
        self.queued.append(normalized)
        value = self.values.get(normalized)
        if value is not None:
            payload = json.loads(self.cache_file.read_text(encoding="utf-8") or "{}")
            payload[normalized] = {
                "float": int(value),
                "source": "YAHOO",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.cache_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return True

    def discover_now(self, symbol: str) -> FloatDiscoveryResult:
        normalized = symbol.upper()
        self.requests.append(normalized)
        return FloatDiscoveryResult(
            symbol=normalized,
            value=None,
            source="UNKNOWN",
            cache_used=False,
            fallback_used=False,
            failures=(("PR1083_BACKGROUND", "foreground_not_expected"),),
        )


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    set_config_overrides({})


def _configure_readonly(*, news_enabled: bool = False) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "EXECUTION_ENABLED_EFFECTIVE": False,
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": False,
            "SCANNER_DATA_SOURCE": "IBKR",
            "SCANNER_MODE": "LIVE_READONLY",
            "IBKR_FALLBACK_ENABLED": False,
            "NEWS_ENABLED": news_enabled,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
            "ALLOW_UNKNOWN_FLOAT": False,
        }
    )


def _install_discovery_worker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, values: dict[str, int | None]) -> _DiscoveryWorkerStub:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    worker = _DiscoveryWorkerStub(values)
    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_file)
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda path: worker)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    return worker


def _install_background_cache_write_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    values: dict[str, int | None],
) -> _BackgroundCacheWriteWorkerStub:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    worker = _BackgroundCacheWriteWorkerStub(cache_file, values)
    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_file)
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda path: worker)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    return worker


def _policy(*, require_catalyst: bool = False):
    return replace(
        RossMomentumPolicy().stock_selection,
        top_gainers_n=3,
        max_symbols_per_cycle=3,
        watchlist_limit_k=2,
        focus_limit_m=1,
        require_catalyst=require_catalyst,
        session_allowlist=("PRE", "REG", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"),
        ranking_intent="ROSS_MOMENTUM_STOCK_SELECTION",
    )


def _ross_row(symbol: str = "PR50A", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol,
        "last": 7.0,
        "prev_close": 5.0,
        "bid": 6.99,
        "ask": 7.01,
        "volume": 1_600_000,
        "avg_volume": 200_000,
        "float_shares": None,
    }
    row.update(overrides)
    return row


def _run_readonly_cycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    discovered_float: int | None,
    row: dict[str, Any] | None = None,
    require_catalyst: bool = False,
):
    _configure_readonly(news_enabled=False)
    symbol = str((row or {}).get("symbol") or "PR50A").upper()
    worker = _install_discovery_worker(monkeypatch, tmp_path, {symbol: discovered_float})
    policy = _policy(require_catalyst=require_catalyst)
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")
    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledRuntimeProvider([row or _ross_row(symbol)]),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR1050_TEST",
    )
    return payload, worker


def _metric_for(payload: dict[str, Any], symbol: str):
    for metric in payload.get("candidate_metrics", []):
        if getattr(metric, "symbol", None) == symbol:
            return metric
    raise AssertionError(f"missing candidate metric for {symbol}")


def test_pr1083_background_cache_write_rehydrates_before_unknown_float_drop_and_adapter_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_readonly(news_enabled=False)
    worker = _install_background_cache_write_worker(monkeypatch, tmp_path, {"AREN": 13_144_349})
    policy = _policy(require_catalyst=False)
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledRuntimeProvider(
            [
                _ross_row(
                    "AREN",
                    last=1.20,
                    prev_close=0.94,
                    bid=None,
                    ask=None,
                    volume=95_209,
                    avg_volume=5_587,
                )
            ]
        ),
        forced_session_label="RTH_MID",
        forced_session_source="PR1083_TEST",
    )

    assert worker.queued == ["AREN"]
    assert worker.requests == []
    assert payload["float_discovery_success_count"] == 1
    assert payload["float_discovery_same_cycle_rehydrated_count"] == 1
    assert payload["float_discovery_failed_count"] == 0
    assert payload["float_unknown_after_bounded_discovery_count"] == 0
    assert payload["symbols_rehydrated_from_same_cycle_float_discovery"] == ["AREN"]
    assert "AREN" not in payload["symbols_still_dropped_float_unknown"]
    assert payload["drop_ledger"].get("AREN") != "DROP_FLOAT_UNKNOWN"
    assert payload["watchlist_k_symbols"] == ["AREN"]

    metric = _metric_for(payload, "AREN")
    assert metric.float_shares == 13_144_349
    assert metric.float_source == "YAHOO"
    assert "FLOAT_UNKNOWN" not in metric.data_quality_flags
    assert metric.volume == 95_209
    assert metric.rvol is not None and metric.rvol > 2.0
    assert metric.gate_checks["watch_rvol"] is True
    assert metric.gate_checks["watch_float"] is True

    proof = payload["float_discovery"]
    evidence = pr1040.RuntimeObservationEvidence(
        operator="TEST_OP",
        scenario_id="PR1083_ADAPTER_TEST",
        env=pr1040.build_safe_readonly_env({}),
        captured_at_utc="2026-08-28T14:55:00+00:00",
        scanner_payload=payload,
        focus_rows=[],
        watchlist_rows=payload.get("watchlist_rows", []),
        pattern_input_evidence=[],
        pattern_summaries=[],
        intent_records=[],
        risk_decisions=[],
        execution_events=[],
        broker_before={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {}},
        broker_after={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {}},
        session_label="RTH_MID",
        storage_write_verified=True,
        storage_readback_verified=True,
        storage_evidence_source=pr1040.REAL_STORAGE_EVIDENCE_SOURCE,
        storage_evidence_detail={"path": "analytics/runtime/pr1083.json"},
    )
    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["scanner_cycle_artifact"]["float_discovery"] == proof
    assert spec["watchlist_focus_artifact"]["float_discovery"] == proof
    assert spec["market_data_observation_diagnostics"]["float_discovery"] == proof
    assert "AREN" in spec["market_data_observation_diagnostics"]["symbols_with_float"]
    assert spec["scanner_cycle_artifact"]["drop_ledger"].get("AREN") != "DROP_FLOAT_UNKNOWN"


def test_pr1083_same_cycle_cache_result_after_runtime_bound_is_not_counted(tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text(
        json.dumps(
            {
                "LATE": {
                    "float": 13_144_349,
                    "source": "YAHOO",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    float_cache: dict[str, dict[str, Any]] = {}
    proof = scanner_runner._empty_float_discovery_proof()
    context = {
        "symbol": "LATE",
        "float_shares": None,
        "float_source": "UNKNOWN",
        "volume": 95_209,
        "rvol": 48.69,
        "data_quality_flags": ["FLOAT_UNKNOWN"],
    }

    consumed = scanner_runner._consume_same_cycle_float_cache_update(
        context,
        float_cache=float_cache,
        cache_path=cache_file,
        proof=proof,
        cycle_started_at_utc=datetime.now(timezone.utc) - timedelta(seconds=1),
        runtime_bound_reached=lambda stage: True,
    )

    assert consumed is False
    assert context["float_shares"] is None
    assert context["volume"] == 95_209
    assert context["rvol"] == 48.69
    assert proof["float_discovery_success_count"] == 0
    assert proof["float_discovery_same_cycle_rehydrated_count"] == 0
    assert proof["symbols_rehydrated_from_same_cycle_float_discovery"] == []


def test_pr1050_same_cycle_float_discovery_rehydrates_before_final_ross_gates(monkeypatch, tmp_path: Path) -> None:
    payload, worker = _run_readonly_cycle(monkeypatch, tmp_path, discovered_float=5_000_000)

    assert worker.queued == ["PR50A"]
    assert worker.requests == ["PR50A"]
    assert payload["watchlist_k_symbols"] == ["PR50A"]
    assert payload["focus_m_symbols"] == ["PR50A"]
    assert payload["drop_ledger"] == {}
    assert payload["float_discovery_requested_count"] == 1
    assert payload["float_discovery_success_count"] == 1
    assert payload["float_discovery_failed_count"] == 0
    assert payload["float_discovery_same_cycle_rehydrated_count"] == 1
    assert payload["float_unknown_after_bounded_discovery_count"] == 0
    assert payload["symbols_rehydrated_from_same_cycle_float_discovery"] == ["PR50A"]
    assert "FLOAT_UNKNOWN" not in payload["data_quality_by_symbol"]["PR50A"]

    metric = _metric_for(payload, "PR50A")
    assert metric.float_shares == 5_000_000
    assert metric.float_source == "PR1050_TEST"
    assert metric.watchlist_source == "LIVE_SCAN"
    assert metric.prep_seeded is False
    assert metric.selection_rationale["final_decision"] == "ACCEPT"
    assert payload["float_focus_diagnostics"]["focus_empty_explanation"] == "FOCUS_M_POPULATED"


def test_pr1050_discovery_failure_keeps_unknown_float_drop_and_no_quality_focus(monkeypatch, tmp_path: Path) -> None:
    payload, worker = _run_readonly_cycle(monkeypatch, tmp_path, discovered_float=None)

    assert worker.requests == ["PR50A"]
    assert payload["watchlist_k_symbols"] == []
    assert payload["focus_m_symbols"] == []
    assert payload["drop_ledger"] == {"PR50A": "DROP_FLOAT_UNKNOWN"}
    assert payload["float_discovery_requested_count"] == 1
    assert payload["float_discovery_success_count"] == 0
    assert payload["float_discovery_failed_count"] == 1
    assert payload["float_discovery_same_cycle_rehydrated_count"] == 0
    assert payload["float_unknown_after_bounded_discovery_count"] == 1
    assert payload["symbols_still_dropped_float_unknown"] == ["PR50A"]
    assert payload["float_focus_diagnostics"]["focus_empty_explanation"] == "USABLE_MARKET_DATA_BUT_UNKNOWN_FLOAT"
    assert payload["float_focus_diagnostics"]["usable_market_data_but_unknown_float_symbols"] == ["PR50A"]

    metric = _metric_for(payload, "PR50A")
    assert metric.float_shares is None
    assert metric.selection_rationale["final_decision"] == "REJECT"
    assert "DROP_FLOAT_UNKNOWN" in metric.drop_reasons


def test_pr1050_over_float_candidate_remains_rejected_after_rehydration(monkeypatch, tmp_path: Path) -> None:
    payload, worker = _run_readonly_cycle(monkeypatch, tmp_path, discovered_float=30_000_000)

    assert worker.requests == ["PR50A"]
    assert payload["watchlist_k_symbols"] == []
    assert payload["focus_m_symbols"] == []
    assert payload["drop_ledger"] == {"PR50A": "DROP_FLOAT_MAX"}
    assert payload["float_discovery_success_count"] == 1
    assert payload["float_discovery_same_cycle_rehydrated_count"] == 1
    assert payload["float_unknown_after_bounded_discovery_count"] == 0
    assert payload["float_focus_diagnostics"]["focus_empty_explanation"] == "USABLE_MARKET_DATA_BUT_OVER_FLOAT"
    assert payload["float_focus_diagnostics"]["usable_market_data_but_over_float_symbols"] == ["PR50A"]


def test_pr1050_rvol_failure_diagnostic_after_float_rehydration(monkeypatch, tmp_path: Path) -> None:
    row = _ross_row(volume=400_000, avg_volume=500_000)
    payload, worker = _run_readonly_cycle(monkeypatch, tmp_path, discovered_float=5_000_000, row=row)

    assert worker.requests == ["PR50A"]
    assert payload["watchlist_k_symbols"] == ["PR50A"]
    assert payload["focus_m_symbols"] == []
    assert payload["float_discovery_success_count"] == 1
    assert payload["float_discovery_same_cycle_rehydrated_count"] == 1
    assert payload["float_focus_diagnostics"]["focus_empty_explanation"] == "USABLE_MARKET_DATA_BUT_RVOL_FAILURE"
    assert payload["float_focus_diagnostics"]["usable_market_data_but_rvol_failure_symbols"] == ["PR50A"]
    assert payload["float_focus_diagnostics"]["focus_drop_reason_counts"] == {"DROP_RVOL_FOCUS": 1}


def test_pr1050_catalyst_failure_diagnostic_without_catalyst_bypass(monkeypatch, tmp_path: Path) -> None:
    payload, worker = _run_readonly_cycle(
        monkeypatch,
        tmp_path,
        discovered_float=5_000_000,
        require_catalyst=True,
    )

    assert worker.requests == ["PR50A"]
    assert payload["watchlist_k_symbols"] == ["PR50A"]
    assert payload["focus_m_symbols"] == []
    assert payload["float_discovery_success_count"] == 1
    assert payload["float_focus_diagnostics"]["focus_empty_explanation"] == "USABLE_MARKET_DATA_BUT_CATALYST_NEWS_FAILURE"
    assert payload["float_focus_diagnostics"]["usable_market_data_but_catalyst_news_failure_symbols"] == ["PR50A"]
    assert payload["float_focus_diagnostics"]["focus_drop_reason_counts"] == {"DROP_NO_CATALYST": 1}
    assert payload["diagnostics"]["news"]["news_gate_bypassed"] is False


def _pr1050_proof() -> dict[str, Any]:
    return {
        "float_discovery_requested_count": 1,
        "float_discovery_success_count": 0,
        "float_discovery_failed_count": 1,
        "float_discovery_cache_hit_count": 0,
        "float_discovery_same_cycle_rehydrated_count": 0,
        "float_discovery_pending_count": 0,
        "float_unknown_after_bounded_discovery_count": 1,
        "symbols_rehydrated_from_same_cycle_float_discovery": [],
        "symbols_still_dropped_float_unknown": ["PR50A"],
        "symbols_pending_same_cycle_float_discovery": [],
        "symbols_failed_same_cycle_float_discovery": ["PR50A"],
        "max_same_cycle_float_discovery_requests": 15,
    }


def test_pr1050_readonly_adapter_propagates_proof_and_keeps_paper_gate_closed() -> None:
    proof = _pr1050_proof()
    focus_diag = {
        "symbols_with_usable_market_data": ["PR50A"],
        "missing_market_data_symbols": [],
        "usable_market_data_but_unknown_float_symbols": ["PR50A"],
        "usable_market_data_but_over_float_symbols": [],
        "usable_market_data_but_rvol_failure_symbols": [],
        "usable_market_data_but_catalyst_news_failure_symbols": [],
        "focus_empty_explanation": "USABLE_MARKET_DATA_BUT_UNKNOWN_FLOAT",
        "focus_drop_reason_counts": {},
    }
    row = {
        "symbol": "PR50A",
        "last_price": 7.0,
        "bid": 6.99,
        "ask": 7.01,
        "volume": 1_600_000,
        "float_shares": None,
        "drop_reasons": ["DROP_FLOAT_UNKNOWN"],
    }
    scanner_payload = {
        "provider_source": "IBKR",
        "symbols": ["PR50A"],
        "topn_count": 1,
        "survivors_count": 0,
        "watchlist_k_symbols": [],
        "focus_m_symbols": [],
        "candidate_metrics": [row],
        "watchlist_rows": [],
        "focus_rows": [],
        "drop_ledger": {"PR50A": "DROP_FLOAT_UNKNOWN"},
        "float_discovery": proof,
        "float_focus_diagnostics": focus_diag,
        "diagnostics": {"float_discovery": proof, "float_focus_diagnostics": focus_diag},
        **proof,
    }
    evidence = pr1040.RuntimeObservationEvidence(
        operator="TEST_OP",
        scenario_id="PR1050_ADAPTER_TEST",
        env=pr1040.build_safe_readonly_env({}),
        captured_at_utc="2026-08-13T12:00:00+00:00",
        scanner_payload=scanner_payload,
        focus_rows=[],
        watchlist_rows=[],
        pattern_input_evidence=[],
        pattern_summaries=[],
        intent_records=[],
        risk_decisions=[],
        execution_events=[],
        broker_before={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {}},
        broker_after={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {}},
        session_label="RTH_OPEN",
        storage_write_verified=True,
        storage_readback_verified=True,
        storage_evidence_source=pr1040.REAL_STORAGE_EVIDENCE_SOURCE,
        storage_evidence_detail={"path": "analytics/runtime/pr1050.json"},
    )

    spec = pr1040.build_pr1039_observation_input(evidence)
    final = spec["final_verdict"]
    market = spec["market_data_observation_diagnostics"]
    scanner_artifact = spec["scanner_cycle_artifact"]
    watchlist_artifact = spec["watchlist_focus_artifact"]
    ibkr = market["ibkr_market_data_diagnostic"]

    assert final["paper_ready"] == "NO"
    assert final["paper_readiness_gate"] == "FAIL"
    assert final["ZERO_BROKER_ORDER_MUTATIONS"] == "YES"
    assert spec["execution_gate_artifact"]["execution_enabled"] is False
    assert spec["execution_gate_artifact"]["order_submission_enabled"] is False
    assert spec["broker_order_audit"]["order_attempt_count"] == 0
    assert market["float_discovery"] == proof
    assert market["float_focus_diagnostics"] == focus_diag
    assert scanner_artifact["float_discovery"] == proof
    assert watchlist_artifact["float_discovery"] == proof
    assert watchlist_artifact["float_focus_diagnostics"] == focus_diag
    assert ibkr["float_discovery"] == proof
    assert ibkr["paper_ready"] == "NO"
    assert ibkr["paper_readiness_gate"] == "FAIL"
