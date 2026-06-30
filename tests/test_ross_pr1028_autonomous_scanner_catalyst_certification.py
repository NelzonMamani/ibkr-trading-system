from __future__ import annotations

from dataclasses import replace

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import (
    _candidate_from_context,
    _evaluate_focus_gates,
    _gate_thresholds,
    _resolve_runtime_thresholds,
)
from src.strategies.ross_momentum.policy import CatalystStatus, assess_catalyst
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    select_watchlist,
)


class _ControlledRuntimeProvider:
    source_name = "TEST"

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = {str(row["symbol"]).upper(): row for row in rows}
        self._symbols = [str(row["symbol"]).upper() for row in rows]
        self.last_scan_details = {
            "requested_location_code": "STK.US",
            "selected_location_code": "STK.US",
            "requested_scan_code": "TOP_PERC_GAIN",
            "selected_scan_code": "TOP_PERC_GAIN",
            "retry_attempts": 0,
            "retry_exhausted": False,
            "returned_rows": len(self._symbols),
            "symbol_details": {
                symbol: {
                    "conId": idx,
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
        selected = self._symbols[:limit]
        self.last_scan_details["returned_rows"] = len(selected)
        return selected

    def get_quote(self, symbol: str) -> QuoteData:
        row = self._rows[symbol.upper()]
        last = float(row["last"])
        prev_close = float(row["prev_close"])
        bid = row.get("bid", round(last - 0.01, 2))
        ask = row.get("ask", round(last + 0.01, 2))
        volume = float(row.get("volume", 1_000_000))
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
            volume=volume,
            timestamp_utc=None,
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> float:
        return float(self._rows[str(symbol).upper()]["prev_close"])

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        row = self._rows[symbol.upper()]
        volume = int(row.get("volume", 1_000_000))
        avg_volume = int(row.get("avg_volume", 200_000))
        rvol = round(volume / avg_volume, 2) if avg_volume else None
        return IntradayStats(
            current_intraday_volume=volume,
            current_volume_source_label="TEST",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=rvol,
            relative_volume_category="HIGH" if rvol and rvol >= 3.0 else "NORMAL",
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str) -> int | None:
        value = self._rows[symbol.upper()].get("float_shares")
        return None if value is None else int(value)

    def get_previous_rth_close(self, identity) -> float:
        return self.get_prev_close(getattr(identity, "symbol", identity))

    def get_average_daily_volume(self, identity, window: int) -> tuple[int, int]:
        symbol = str(getattr(identity, "symbol", identity)).upper()
        return int(self._rows[symbol].get("avg_volume", 200_000)), min(window, 20)

    def get_daily_bars(self, identity, lookback_days: int):
        symbol = str(getattr(identity, "symbol", identity)).upper()
        prev_close = self.get_prev_close(symbol)
        avg_volume, window = self.get_average_daily_volume(symbol, lookback_days)
        return [
            type(
                "Bar",
                (),
                {"date": f"2026-01-{idx + 1:02d}", "close": prev_close, "volume": avg_volume},
            )()
            for idx in range(window)
        ]


@pytest.fixture(autouse=True)
def _reset_scanner_state():
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})


def _cert_policy(*, require_catalyst: bool):
    return replace(
        RossMomentumPolicy().stock_selection,
        top_gainers_n=6,
        max_symbols_per_cycle=6,
        watchlist_limit_k=3,
        focus_limit_m=2,
        require_catalyst=require_catalyst,
        session_allowlist=("PRE", "REG", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"),
        ranking_intent="ROSS_MOMENTUM_STOCK_SELECTION",
    )


def _thresholds_for(session: str, *, policy=None, mode: str = "READ_ONLY"):
    set_config_overrides({"RUN_MODE": mode, "NEWS_ENABLED": False, "IBKR_FALLBACK_ENABLED": False})
    stock_policy = policy or _cert_policy(require_catalyst=True)
    runtime = _resolve_runtime_thresholds(stock_policy, session)
    return _gate_thresholds(stock_policy, runtime)


def _focus_context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "symbol": "PR28CAT",
        "session": "RTH_OPEN",
        "pct_change": 24.0,
        "pct_change_resolved": 24.0,
        "pct_source": "TEST",
        "reference_source": "TEST",
        "scanner_rvol": 6.5,
        "rvol": 6.5,
        "rvol_phase": 6.5,
        "rvol_discovery": 6.5,
        "volume": 1_500_000,
        "premarket_volume": 1_500_000,
        "avg_volume_20d": 230_000,
        "dollar_volume": 10_500_000,
        "last_price": 7.0,
        "float_shares": 6_000_000,
        "spread_pct": 0.004,
        "bid": 6.99,
        "ask": 7.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
        "scanner_score": 96.0,
        "scanner_score_components": {"pct_change": 45.0, "rvol": 35.0, "dollar_volume": 20.0},
    }
    context.update(overrides)
    return context


def _quality_rows() -> list[dict[str, object]]:
    return [
        {"symbol": "PR28A", "last": 7.0, "prev_close": 5.0, "volume": 1_800_000, "avg_volume": 200_000, "float_shares": 5_000_000},
        {"symbol": "PR28B", "last": 8.0, "prev_close": 6.0, "volume": 1_500_000, "avg_volume": 250_000, "float_shares": 6_000_000},
        {"symbol": "PR28C", "last": 6.0, "prev_close": 5.0, "volume": 1_200_000, "avg_volume": 260_000, "float_shares": 8_000_000},
        {"symbol": "PR28D", "last": 5.8, "prev_close": 5.0, "volume": 1_100_000, "avg_volume": 300_000, "float_shares": 9_000_000},
    ]


def test_pr1028_readonly_scanner_cycle_ranks_watchlist_and_focus_without_manual_focus(capsys) -> None:
    set_config_overrides({"RUN_MODE": "READ_ONLY", "NEWS_ENABLED": False, "IBKR_FALLBACK_ENABLED": False})
    policy = _cert_policy(require_catalyst=False)
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledRuntimeProvider(_quality_rows()),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR1028_TEST",
    )
    output = capsys.readouterr().out

    result = payload["scanner_result"]
    assert result.top_n_symbols == ["PR28A", "PR28B", "PR28C", "PR28D"]
    assert 1 <= len(result.watchlist_k) <= policy.watchlist_limit_k
    assert 1 <= len(result.focus_m) <= policy.focus_limit_m
    assert {row.symbol for row in result.focus_m}.issubset({row.symbol for row in result.watchlist_k})
    assert payload["watchlist_k_symbols"] == [row.symbol for row in result.watchlist_k]
    assert payload["focus_m_symbols"] == [row.symbol for row in result.focus_m]
    assert payload["diagnostics"]["scanner_contract"]["contract_valid"] is True
    assert payload["diagnostics"]["selection_spec"]["ranking_intent"] == "ROSS_MOMENTUM_STOCK_SELECTION"
    assert payload["diagnostics"]["provider_source"] == "TEST"
    assert all(row.watchlist_source != "manual_focus" for row in result.watchlist_k)
    assert all(not row.prep_seeded for row in result.watchlist_k)
    assert "[SCANNER][ENTRY]" in output
    assert "[ROSS][WATCHLIST][ACCEPT]" in output
    assert "[ROSS][FOCUS][ACCEPT]" in output
    assert "[SCANNER][CONTRACT]" in output


def test_pr1028_hard_scanner_rejections_do_not_enter_watchlist_or_focus() -> None:
    set_config_overrides({"RUN_MODE": "READ_ONLY", "NEWS_ENABLED": False, "IBKR_FALLBACK_ENABLED": False})
    policy = _cert_policy(require_catalyst=False)
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")
    rows = [
        {"symbol": "PR28HFLT", "last": 7.0, "prev_close": 5.0, "volume": 1_600_000, "avg_volume": 200_000, "float_shares": 30_000_000},
        {"symbol": "PR28UFLT", "last": 7.0, "prev_close": 5.0, "volume": 1_600_000, "avg_volume": 200_000, "float_shares": None},
        {"symbol": "PR28WGAP", "last": 5.2, "prev_close": 5.0, "volume": 1_600_000, "avg_volume": 200_000, "float_shares": 6_000_000},
        {"symbol": "PR28LRVL", "last": 7.0, "prev_close": 5.0, "volume": 250_000, "avg_volume": 250_000, "float_shares": 6_000_000},
    ]

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledRuntimeProvider(rows),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR1028_TEST",
    )

    rejected = {"PR28HFLT", "PR28UFLT", "PR28WGAP", "PR28LRVL"}
    assert payload["scanner_result"].top_n_symbols == [str(row["symbol"]) for row in rows]
    assert payload["watchlist_k_symbols"] == []
    assert payload["focus_m_symbols"] == []
    assert rejected.issubset(set(payload["drop_ledger"].keys()))
    assert set(payload["drop_ledger"].values()).issuperset(
        {"DROP_FLOAT_MAX", "DROP_FLOAT_UNKNOWN", "DROP_PCT_CHANGE", "DROP_RVOL_DISCOVERY"}
    )
    assert payload["diagnostics"]["scanner_contract"]["contract_valid"] is True


def test_pr1028_catalyst_context_is_preserved_and_missing_catalyst_blocks_selection() -> None:
    policy = _cert_policy(require_catalyst=True)
    thresholds = _thresholds_for("RTH_OPEN", policy=policy)
    timestamp = "2026-06-30T12:00:00+00:00"
    confirmed_news = {
        "news_present": True,
        "ross_catalyst_valid": True,
        "catalyst_type": "EARNINGS",
        "news_age_minutes": 12,
        "news_count": 1,
        "fresh_news_count": 1,
        "stale_news_count": 0,
        "top_news_title": "PR28CAT reports earnings beat and raises guidance",
        "top_news_age_hours": 0.2,
        "top_news_catalyst_tag": "EARNINGS",
        "news_source_mode": "fixture",
        "news_asof": timestamp,
    }
    missing_news = {
        "news_present": False,
        "ross_catalyst_valid": False,
        "news_count": 0,
        "fresh_news_count": 0,
        "stale_news_count": 0,
        "news_source_mode": "fixture",
        "news_asof": timestamp,
    }

    confirmed = _candidate_from_context(
        _focus_context(symbol="PR28CAT"),
        confirmed_news,
        thresholds,
        drop_reason=None,
        timestamp_utc=timestamp,
    )
    missing = _candidate_from_context(
        _focus_context(symbol="PR28MISS"),
        missing_news,
        thresholds,
        drop_reason=None,
        timestamp_utc=timestamp,
    )

    assert confirmed.catalyst_present is True
    assert confirmed.catalyst_summary == "EARNINGS age=12m"
    assert confirmed.news_count == 1
    assert confirmed.fresh_news_count == 1
    assert confirmed.top_news_catalyst_tag == "EARNINGS"
    assert confirmed.news_source_mode == "fixture"
    assert confirmed.gate_checks["catalyst_ok"] is True
    assert confirmed.selection_rationale["catalyst"] == "PRESENT"
    assert missing.catalyst_present is False
    assert missing.gate_checks["catalyst_ok"] is False
    assert select_watchlist([confirmed, missing], policy=policy) == [confirmed]
    assert _evaluate_focus_gates(
        _focus_context(
            symbol="PR28MISS",
            catalyst_present=False,
            news_present=False,
            catalyst_summary=None,
            catalyst_status="DATA_UNAVAILABLE",
        ),
        thresholds,
    ) == "DROP_NO_CATALYST"


def test_pr1028_catalyst_policy_status_matrix_blocks_live_like_bypass() -> None:
    confirmed = assess_catalyst(
        mode="READ_ONLY",
        news_enabled=True,
        news_available=True,
        confirmed=True,
    )
    absent = assess_catalyst(
        mode="READ_ONLY",
        news_enabled=True,
        news_available=True,
        confirmed=False,
    )
    unknown = assess_catalyst(
        mode="READ_ONLY",
        news_enabled=True,
        news_available=True,
        confirmed=None,
    )
    unavailable = assess_catalyst(
        mode="READ_ONLY",
        news_enabled=True,
        news_available=False,
        confirmed=None,
    )
    paper_validation = assess_catalyst(
        mode="PAPER",
        news_enabled=False,
        news_available=False,
        confirmed=None,
        validation_bypass_requested=True,
    )
    readonly_validation = assess_catalyst(
        mode="READ_ONLY",
        news_enabled=False,
        news_available=False,
        confirmed=None,
        validation_bypass_requested=True,
    )

    assert confirmed.status is CatalystStatus.CONFIRMED
    assert confirmed.satisfied is True
    assert absent.status is CatalystStatus.ABSENT
    assert absent.satisfied is False
    assert unknown.status is CatalystStatus.UNKNOWN
    assert unknown.satisfied is False
    assert unavailable.status is CatalystStatus.DATA_UNAVAILABLE
    assert unavailable.reason == "news_unavailable"
    assert unavailable.satisfied is False
    assert paper_validation.status is CatalystStatus.DISABLED_FOR_VALIDATION
    assert paper_validation.satisfied is True
    assert readonly_validation.status is CatalystStatus.DATA_UNAVAILABLE
    assert readonly_validation.reason == "news_disabled"
    assert readonly_validation.satisfied is False
