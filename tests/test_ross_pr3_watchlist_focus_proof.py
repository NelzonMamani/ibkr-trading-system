from __future__ import annotations

from dataclasses import replace

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import (
    _candidate_from_context,
    _evaluate_gates,
    _evaluate_focus_gates,
    _forced_premarket_focus_eligible,
    _gate_thresholds,
    _resolve_runtime_thresholds,
)
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    select_watchlist,
)


class _ControlledProvider:
    source_name = "TEST"

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = {str(row["symbol"]).upper(): row for row in rows}
        self._symbols = [str(row["symbol"]).upper() for row in rows]

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        return self._symbols[:limit]

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
        return float(self._rows[symbol.upper()]["prev_close"])

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
        symbol = getattr(identity, "symbol", identity)
        return int(self._rows[str(symbol).upper()].get("avg_volume", 200_000)), min(window, 20)

    def get_daily_bars(self, identity, lookback_days: int):
        symbol = str(getattr(identity, "symbol", identity)).upper()
        prev_close = self.get_prev_close(symbol)
        avg_volume, window = self.get_average_daily_volume(symbol, lookback_days)
        return [
            type("Bar", (), {"date": f"2026-01-{idx + 1:02d}", "close": prev_close, "volume": avg_volume})()
            for idx in range(window)
        ]


@pytest.fixture(autouse=True)
def _reset_state():
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})


def _thresholds_for(session: str, *, mode: str = "LIVE", policy=None):
    set_config_overrides({"RUN_MODE": mode})
    stock_policy = policy or RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(stock_policy, session)
    return _gate_thresholds(stock_policy, runtime)


def _focus_context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "symbol": "ROSSX",
        "session": "RTH_OPEN",
        "pct_change": 18.0,
        "scanner_rvol": 5.5,
        "rvol": 5.5,
        "rvol_phase": 5.5,
        "rvol_discovery": 5.5,
        "volume": 1_000_000,
        "premarket_volume": 1_000_000,
        "dollar_volume": 5_000_000,
        "last_price": 7.0,
        "float_shares": 8_000_000,
        "spread_pct": 0.01,
        "bid": 6.99,
        "ask": 7.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }
    context.update(overrides)
    return context


def _flow_policy():
    return replace(
        RossMomentumPolicy().stock_selection,
        top_gainers_n=4,
        max_symbols_per_cycle=4,
        watchlist_limit_k=2,
        focus_limit_m=1,
        require_catalyst=False,
        session_allowlist=("PRE", "REG", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"),
        ranking_intent="ROSS_MOMENTUM_STOCK_SELECTION",
    )


def _quality_rows() -> list[dict[str, object]]:
    return [
        {"symbol": "AAA", "last": 7.0, "prev_close": 5.0, "volume": 1_600_000, "avg_volume": 200_000, "float_shares": 5_000_000},
        {"symbol": "BBB", "last": 8.0, "prev_close": 6.0, "volume": 1_200_000, "avg_volume": 200_000, "float_shares": 6_000_000},
        {"symbol": "CCC", "last": 9.0, "prev_close": 7.5, "volume": 1_000_000, "avg_volume": 250_000, "float_shares": 7_000_000},
        {"symbol": "DDD", "last": 10.0, "prev_close": 9.0, "volume": 900_000, "avg_volume": 250_000, "float_shares": 8_000_000},
    ]


def test_topn_watchlist_focus_flow_sizes_state_and_logs(capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "ROSS_VALIDATION_OVERRIDE_ENABLED": True,
            "NEWS_ENABLED": False,
        }
    )
    policy = _flow_policy()
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")

    first = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledProvider(_quality_rows()),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR3_TEST",
    )
    first_output = capsys.readouterr().out

    result = first["scanner_result"]
    assert result.top_n_symbols == ["AAA", "BBB", "CCC", "DDD"]
    assert len(result.watchlist_k) <= policy.watchlist_limit_k
    assert len(result.focus_m) <= policy.focus_limit_m
    assert {row.symbol for row in result.focus_m}.issubset({row.symbol for row in result.watchlist_k})
    assert first["diagnostics"]["scanner_contract"]["contract_valid"] is True
    assert set(result.new_symbols) == {row.symbol for row in result.watchlist_k}
    assert "[ROSS][WATCHLIST][EVAL]" in first_output
    assert "[ROSS][WATCHLIST][ACCEPT]" in first_output
    assert "[ROSS][WATCHLIST][STATE]" in first_output
    assert "[ROSS][FOCUS][EVAL]" in first_output
    assert "[ROSS][FOCUS][ACCEPT]" in first_output
    assert "[ROSS][FOCUS][SUMMARY]" in first_output

    scanner_runner._LAST_BROKER_SCAN_TS = None
    second = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledProvider(_quality_rows()),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR3_TEST",
    )
    assert set(second["scanner_result"].continuing_symbols) == {
        row.symbol for row in second["scanner_result"].watchlist_k
    }

    scanner_runner._LAST_BROKER_SCAN_TS = None
    bad_rows = [
        {"symbol": row["symbol"], "last": 25.0, "prev_close": 20.0, "volume": row["volume"], "avg_volume": row["avg_volume"], "float_shares": row["float_shares"]}
        for row in _quality_rows()
    ]
    dropped = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledProvider(bad_rows),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR3_TEST",
    )
    assert dropped["scanner_result"].watchlist_k == []
    assert dropped["scanner_result"].focus_m == []
    assert set(second["watchlist_k_symbols"]).issubset(set(dropped["scanner_result"].dropped_symbols))


def test_empty_watchlist_and_focus_are_valid_when_no_symbol_qualifies() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "ROSS_VALIDATION_OVERRIDE_ENABLED": True})
    policy = _flow_policy()
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")
    rows = [
        {"symbol": "BAD1", "last": 25.0, "prev_close": 20.0, "volume": 1_000_000, "avg_volume": 200_000, "float_shares": 5_000_000},
        {"symbol": "BAD2", "last": 0.5, "prev_close": 0.4, "volume": 1_000_000, "avg_volume": 200_000, "float_shares": 5_000_000},
    ]

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
        provider=_ControlledProvider(rows),
        forced_session_label="RTH_OPEN",
        forced_session_source="PR3_TEST",
    )

    assert payload["scanner_result"].top_n_symbols == ["BAD1", "BAD2"]
    assert payload["scanner_result"].watchlist_k == []
    assert payload["scanner_result"].focus_m == []
    assert payload["diagnostics"]["scanner_contract"]["contract_valid"] is True


def test_candidate_rationale_exposes_compact_classifications() -> None:
    thresholds = _thresholds_for("RTH_OPEN")
    candidate = _candidate_from_context(
        _focus_context(pct_source="IBKR", reference_source="IBKR"),
        {"news_present": True, "catalyst_type": "CONTRACT", "news_count": 1},
        thresholds,
        drop_reason=None,
        timestamp_utc="2026-06-12T00:00:00+00:00",
    )

    rationale = candidate.selection_rationale
    assert rationale["price"] in {"LIVE_QUALITY", "PREFERRED_SWEET_SPOT"}
    assert rationale["pct_change"] == "LIVE_QUALITY"
    assert rationale["pct_change_source"] == "IBKR"
    assert rationale["rvol"] == "LIVE_QUALITY"
    assert rationale["float"] == "EXCELLENT_LOW_FLOAT"
    assert rationale["catalyst"] == "PRESENT"
    assert rationale["spread_liquidity"] == "OK"
    assert rationale["session"] == "RTH_OPEN"
    assert rationale["final_decision"] == "ACCEPT"


def test_price_rejected_symbol_cannot_leak_through_selector_into_watchlist() -> None:
    policy = replace(RossMomentumPolicy().stock_selection, watchlist_limit_k=3)
    thresholds = _thresholds_for("RTH_OPEN", policy=policy)
    metric = _candidate_from_context(
        _focus_context(symbol="HIGH", last_price=25.0),
        {"news_present": True},
        thresholds,
        drop_reason="DROP_PRICE_RANGE",
        timestamp_utc="2026-06-12T00:00:00+00:00",
    )

    assert metric.gate_checks["watch_price"] is False
    assert select_watchlist([metric], policy=policy) == []


@pytest.mark.parametrize(
    ("label", "context_overrides", "policy_overrides", "runtime_reason"),
    [
        ("DROP_PRICE_RANGE", {"last_price": 25.0}, {}, "DROP_PRICE_RANGE"),
        ("DROP_FLOAT_UNKNOWN", {"float_shares": None}, {}, "DROP_FLOAT_UNKNOWN"),
        ("DROP_FLOAT_MAX", {"float_shares": 25_000_000}, {}, "DROP_FLOAT_MAX"),
        ("DROP_NO_CATALYST", {"catalyst_present": False, "catalyst_status": "DATA_UNAVAILABLE"}, {}, "DROP_NO_CATALYST"),
        ("DROP_LOW_RVOL", {"scanner_rvol": 1.6, "rvol": 1.6, "rvol_phase": 1.6, "rvol_discovery": 1.6}, {}, "DROP_RVOL_FOCUS"),
        ("DROP_LOW_PCT_CHANGE", {"pct_change": 7.0}, {}, "DROP_PCT_CHANGE_FOCUS"),
        ("DROP_SPREAD", {"spread_pct": 0.10}, {"spread_max_pct": 0.02}, "DROP_SPREAD"),
        ("DROP_LIQUIDITY", {"dollar_volume": 100_000}, {"liquidity_min_dollar_volume": 1_000_000.0}, "DROP_DOLLAR_VOLUME"),
        ("DROP_DATA_QUALITY", {"bid": None, "ask": None}, {"data_quality_require_bid_ask": True}, "DROP_MISSING_BID_ASK"),
    ],
)
def test_hard_rejections_cannot_enter_focus_m(label, context_overrides, policy_overrides, runtime_reason) -> None:
    policy = replace(RossMomentumPolicy().stock_selection, **policy_overrides)
    thresholds = _thresholds_for("RTH_OPEN", policy=policy)
    context = _focus_context(**context_overrides)

    assert _evaluate_gates(context, thresholds) == runtime_reason
    blocked = _focus_context(session="PRE")
    blocked["focus_drop_reason" if runtime_reason not in {"DROP_FLOAT_UNKNOWN", "DROP_FLOAT_MAX"} else "drop_reason"] = runtime_reason
    assert _forced_premarket_focus_eligible(blocked, thresholds, session_label="PRE") is False
    assert label.startswith("DROP_")


def test_low_price_and_manual_focus_are_not_live_quality_bypasses() -> None:
    thresholds = _thresholds_for("RTH_OPEN")
    low_price = _focus_context(last_price=1.5)

    assert _evaluate_focus_gates(low_price, thresholds) is None
    assert low_price["price_quality"] == "LOW_PRICE_DEGRADED"
    assert low_price["execution_eligible"] is False
    assert low_price["selection_tier"] == "DISCOVERY"

    manual_focus = _focus_context(symbol_source="manual_focus", pct_change=7.0)
    assert _evaluate_focus_gates(manual_focus, thresholds) == "DROP_PCT_CHANGE_FOCUS"


@pytest.mark.parametrize(
    ("session", "focus_rvol_min", "watch_pct_min", "focus_pct_min"),
    [
        ("PRE", 2.0, 5.0, 5.0),
        ("RTH_OPEN", 2.5, 5.0, 10.0),
        ("RTH_MID", 2.0, 5.0, 10.0),
        ("RTH_LATE", 1.5, 5.0, 10.0),
        ("AH", 1.25, 5.0, 5.0),
        ("OVN", 1.0, 5.0, 5.0),
        ("WEEKEND", 999.0, 5.0, 10.0),
    ],
)
def test_session_thresholds_preserve_rvol_and_pct_policy(session, focus_rvol_min, watch_pct_min, focus_pct_min) -> None:
    thresholds = _thresholds_for(session)

    assert thresholds.focus_rvol_min == focus_rvol_min
    assert thresholds.min_pct_change == watch_pct_min
    assert thresholds.focus_pct_change_min == focus_pct_min
    assert thresholds.live_quality_pct_change_min == 10.0


def test_pre_forced_promotion_cannot_bypass_final_gates() -> None:
    thresholds = _thresholds_for("PRE")
    cases = [
        {"catalyst_present": False, "catalyst_status": "DATA_UNAVAILABLE"},
        {"last_price": 25.0},
        {"float_shares": None},
        {"float_shares": 25_000_000},
        {"pct_change": 4.0},
        {"scanner_rvol": 1.0, "rvol": 1.0, "rvol_phase": 1.0, "rvol_discovery": 1.0},
    ]

    for overrides in cases:
        assert _forced_premarket_focus_eligible(
            _focus_context(session="PRE", **overrides),
            thresholds,
            session_label="PRE",
        ) is False
