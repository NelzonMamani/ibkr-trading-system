from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import scanner_request_from_policy
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


class _RuntimeProvider:
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
                    "conId": 951_000 + idx,
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
        pct_change = round(((last - prev_close) / prev_close) * 100.0, 2)
        return QuoteData(
            symbol=symbol,
            bid=float(row.get("bid", 6.99)),
            ask=float(row.get("ask", 7.01)),
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
            current_volume_source_label="PR1051_TEST",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=rvol,
            relative_volume_category="HIGH" if rvol and rvol >= 3.0 else "NORMAL",
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="PR1051_TEST",
        )

    def get_float(self, symbol: str) -> int | None:
        return int(self._rows[symbol.upper()].get("float_shares", 5_000_000))

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


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})


def _configure_readonly(*, news_enabled: bool) -> None:
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


def _policy():
    return replace(
        RossMomentumPolicy().stock_selection,
        top_gainers_n=1,
        max_symbols_per_cycle=1,
        watchlist_limit_k=1,
        focus_limit_m=1,
        require_catalyst=True,
        session_allowlist=("RTH_OPEN", "PRE", "RTH_MID", "RTH_LATE", "AH", "OVN"),
        ranking_intent="ROSS_MOMENTUM_STOCK_SELECTION",
    )


def _row(symbol: str = "PR51A") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "last": 7.0,
        "prev_close": 5.0,
        "bid": 6.99,
        "ask": 7.01,
        "volume": 1_600_000,
        "avg_volume": 200_000,
        "float_shares": 5_000_000,
    }


def _seed_float_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, symbol: str = "PR51A") -> None:
    cache_path = tmp_path / "float_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                symbol: {
                    "float_value": 5_000_000,
                    "float_source": "PR1051_TEST",
                    "float_asof": "2026-08-19T00:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_path)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}


def _summary(*, total: int = 2, failures: int = 0, reason: str | None = None):
    return SimpleNamespace(
        total_sources=total,
        failure_count=failures,
        failures_by_domain={"news.example": {"TIMEOUT": failures}} if failures else {},
        reason=reason,
    )


def _headline(title: str, *, age_seconds: int = 300):
    return scanner_runner.Headline(
        title=title,
        source="PR1051_NEWS",
        published_ts=time.time() - age_seconds,
        url="https://news.example/pr1051",
    )


def _patch_news(monkeypatch: pytest.MonkeyPatch, headlines: list[Any], summary=None) -> None:
    resolved_summary = summary or _summary()

    def fake_fetch(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: list(headlines) for symbol in symbols}, resolved_summary

    def fake_extended_fetch(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(total=len(sources), failures=0)

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fetch)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended_fetch)


def _run_cycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, news_enabled: bool, headlines: list[Any], summary=None):
    _configure_readonly(news_enabled=news_enabled)
    _seed_float_cache(monkeypatch, tmp_path)
    _patch_news(monkeypatch, headlines, summary)
    policy = _policy()
    return scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=scanner_request_from_policy(policy, strategy_name="ross_momentum"),
        provider=_RuntimeProvider([_row()]),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR1051_TEST",
    )


def test_pr1051_news_config_disabled_fails_closed_with_diagnostics(monkeypatch, tmp_path: Path) -> None:
    payload = _run_cycle(monkeypatch, tmp_path, news_enabled=False, headlines=[])

    news = payload["diagnostics"]["news"]
    assert payload["focus_m_symbols"] == []
    assert news["news_skipped"] is True
    assert news["provider_status"] == "provider_disabled"
    assert news["result_status_counts"] == {"provider_disabled": 1}
    assert payload["float_focus_diagnostics"]["focus_drop_reason_counts"] == {"DROP_NO_CATALYST": 1}


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (_summary(total=2, failures=2, reason="feedparser_missing"), "provider_unavailable"),
        (_summary(total=2, failures=2, reason=None), "provider_request_failure"),
    ],
)
def test_pr1051_provider_unavailable_or_request_failure_is_data_unavailable(monkeypatch, summary, expected) -> None:
    _patch_news(monkeypatch, [], summary)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR51A"], "IBKR")

    assert diagnostics.provider_status == expected
    assert diagnostics.result_status_counts == {expected: 1}
    assert news_by_symbol["PR51A"]["news_available"] is False
    assert news_by_symbol["PR51A"]["ross_catalyst_valid"] is False


def test_pr1051_no_recent_news_is_absent_not_confirmed(monkeypatch) -> None:
    _patch_news(monkeypatch, [], _summary())

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR51A"], "IBKR")

    assert diagnostics.provider_status == "available"
    assert diagnostics.result_status_counts == {"no_recent_news": 1}
    assert news_by_symbol["PR51A"]["news_available"] is True
    assert news_by_symbol["PR51A"]["ross_catalyst_valid"] is False


def test_pr1051_news_present_but_non_qualifying_is_not_catalyst(monkeypatch, tmp_path: Path) -> None:
    payload = _run_cycle(
        monkeypatch,
        tmp_path,
        news_enabled=True,
        headlines=[_headline("PR51A mentioned in morning market wrap")],
    )

    news = payload["diagnostics"]["news"]
    assert payload["focus_m_symbols"] == []
    assert news["news_skipped"] is False
    assert news["provider_status"] == "available"
    assert news["news_present_non_qualifying_count"] == 1
    assert payload["float_focus_diagnostics"]["focus_drop_reason_counts"] == {"DROP_NO_CATALYST": 1}


def test_pr1051_confirmed_catalyst_can_pass_existing_focus_gate(monkeypatch, tmp_path: Path) -> None:
    payload = _run_cycle(
        monkeypatch,
        tmp_path,
        news_enabled=True,
        headlines=[_headline("PR51A reports earnings beat and raises guidance")],
    )

    news = payload["diagnostics"]["news"]
    assert payload["watchlist_k_symbols"] == ["PR51A"]
    assert payload["focus_m_symbols"] == ["PR51A"]
    assert news["news_skipped"] is False
    assert news["provider_status"] == "available"
    assert news["confirmed_catalyst_count"] == 1


def test_pr1051_focus_stage_catalyst_drop_precedes_earlier_unknown_float() -> None:
    usable_float_drop = {
        "symbol": "FLUNKF",
        "last_price": 7.0,
        "bid": 6.99,
        "ask": 7.01,
        "volume": 1_600_000,
    }
    focus_drop = {
        "symbol": "PR51A",
        "last_price": 7.0,
        "bid": 6.99,
        "ask": 7.01,
        "volume": 1_600_000,
        "focus_drop_reason": "DROP_NO_CATALYST",
    }

    diagnostics = scanner_runner._float_focus_failure_diagnostics(
        evaluated_contexts=[usable_float_drop, focus_drop],
        watchlist_contexts=[focus_drop],
        focus_symbols=[],
        drop_ledger={"FLUNKF": "DROP_FLOAT_UNKNOWN"},
    )

    assert diagnostics["focus_empty_explanation"] == "USABLE_MARKET_DATA_BUT_CATALYST_NEWS_FAILURE"
    assert diagnostics["usable_market_data_but_unknown_float_symbols"] == ["FLUNKF"]
    assert diagnostics["usable_market_data_but_catalyst_news_failure_symbols"] == ["PR51A"]
