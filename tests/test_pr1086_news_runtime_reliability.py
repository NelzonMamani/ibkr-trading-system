from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import news_fetcher
from src.scanner import scanner_runner
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import scanner_request_from_policy
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


_FLOAT_CACHE_ASOF = "2026-08-31T00:00:00+00:00"


class _MetadataRuntimeProvider:
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
                    "conId": 1_086_000 + idx,
                    "secType": "STK",
                    "exchange": "SMART",
                    "primaryExchange": "NASDAQ",
                    "tradingClass": symbol,
                    "localSymbol": symbol,
                    "currency": "USD",
                    "longName": str(row.get("longName") or ""),
                }
                for idx, (symbol, row) in enumerate(self._rows.items(), start=1)
            },
        }

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        selected = self._symbols[:limit]
        self.last_scan_details["returned_rows"] = len(selected)
        return selected

    def get_quote(self, symbol: str) -> QuoteData:
        row = self._rows[str(symbol).upper()]
        last = float(row.get("last", 7.0))
        prev_close = float(row.get("prev_close", 5.0))
        pct_change = round(((last - prev_close) / prev_close) * 100.0, 2)
        return QuoteData(
            symbol=symbol,
            bid=float(row.get("bid", round(last - 0.01, 2))),
            ask=float(row.get("ask", round(last + 0.01, 2))),
            last=last,
            vwap=last,
            open=prev_close,
            high=round(last * 1.05, 2),
            low=round(last * 0.95, 2),
            close=prev_close,
            change_percent=pct_change,
            volume=float(row.get("volume", 1_600_000)),
            timestamp_utc=None,
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> float:
        return float(self._rows[str(symbol).upper()].get("prev_close", 5.0))

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        row = self._rows[str(symbol).upper()]
        volume = int(row.get("volume", 1_600_000))
        avg_volume = int(row.get("avg_volume", 200_000))
        rvol = round(volume / avg_volume, 2) if avg_volume else None
        return IntradayStats(
            current_intraday_volume=volume,
            current_volume_source_label="PR1086_TEST",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=rvol,
            relative_volume_category="HIGH" if rvol and rvol >= 3.0 else "NORMAL",
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="PR1086_TEST",
        )

    def get_float(self, symbol: str) -> int | None:
        return int(self._rows[str(symbol).upper()].get("float_shares", 5_000_000))

    def get_previous_rth_close(self, identity) -> float:
        return self.get_prev_close(getattr(identity, "symbol", identity))

    def get_average_daily_volume(self, identity, window: int) -> tuple[int, int]:
        symbol = str(getattr(identity, "symbol", identity)).upper()
        return int(self._rows[symbol].get("avg_volume", 200_000)), min(window, 20)

    def get_daily_bars(self, identity, lookback_days: int, **kwargs):
        symbol = str(getattr(identity, "symbol", identity)).upper()
        prev_close = self.get_prev_close(symbol)
        avg_volume, window = self.get_average_daily_volume(symbol, lookback_days)
        return [
            SimpleNamespace(date=f"2026-08-{idx + 1:02d}", close=prev_close, volume=avg_volume)
            for idx in range(window)
        ]


@pytest.fixture(autouse=True)
def _reset_runtime_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEWS_CACHE_FILE", str(tmp_path / "pr1086_news_cache.json"))
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})


def _configure_readonly(cache_path: Path) -> None:
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
            "NEWS_ENABLED": True,
            "NEWS_CACHE_FILE": str(cache_path),
            "NEWS_TOTAL_BUDGET_S": 8.0,
            "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
            "NEWS_REQUEST_TIMEOUT_S": 5,
            "NEWS_LOOKBACK_HOURS": 6.0,
            "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
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


def _seed_float_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, symbol: str) -> None:
    cache_path = tmp_path / "float_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                symbol: {
                    "float_value": 5_000_000,
                    "float_source": "PR1086_TEST",
                    "float_asof": _FLOAT_CACHE_ASOF,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_path)
    scanner_runner._FLOAT_CACHE_STATE = {"mtime_ns": None, "data": {}}


def _entry(title: str):
    return SimpleNamespace(
        title=title,
        summary="Fresh issuer-name-only catalyst item.",
        link="https://news.example/redhill-biopharma-fda-approval",
        published_parsed=time.gmtime(time.time() - 180),
    )


def _feed(title: str, entries: list[object]):
    return SimpleNamespace(feed={"title": title}, entries=entries)


def test_pr1086_live_scanner_news_uses_scan_metadata_for_company_name_only_catalyst(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_readonly(tmp_path / "pr1086_news_cache.json")
    _seed_float_cache(monkeypatch, tmp_path, "RDHL")
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(
        news_fetcher,
        "_fetch_feed",
        lambda url, timeout_s: _feed(
            "PR1086 Fast Feed",
            [_entry("RedHill Biopharma receives FDA approval for lead therapy")],
        ),
    )

    def fail_extended(*args, **kwargs):  # pragma: no cover - fast match should stop fallback
        raise AssertionError("extended fallback should not run after company-name fast catalyst confirmation")

    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fail_extended)

    policy = _policy()
    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=scanner_request_from_policy(policy, strategy_name="ross_momentum"),
        provider=_MetadataRuntimeProvider(
            [
                {
                    "symbol": "RDHL",
                    "longName": "RedHill Biopharma Ltd.",
                    "last": 7.0,
                    "prev_close": 5.0,
                    "volume": 1_600_000,
                    "avg_volume": 200_000,
                    "float_shares": 5_000_000,
                }
            ]
        ),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR1086_TEST",
    )

    news = payload["diagnostics"]["news"]
    assert payload["watchlist_k_symbols"] == ["RDHL"]
    assert payload["focus_m_symbols"] == ["RDHL"]
    assert news["provider_status"] == "available"
    assert news["result_status_counts"] == {"catalyst_confirmed": 1}
    assert news["confirmed_catalyst_count"] == 1
    assert news["company_name_match_count"] == 1
    assert news["ticker_token_match_count"] == 0
    assert news["news_budget_exhausted"] is False
    assert news["source_provenance_by_symbol"]["RDHL"][0]["source_group"] == "FAST_TRADING"
