from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Optional
from zoneinfo import ZoneInfo

import pytest

from src.scanner import scanner_runner
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.reference_resolver import CanonicalReferenceResolver, HistoricalDailyBar, PersistentReferenceCache
from src.scanner.scanner_runner import GateThresholds, _build_symbol_context, _evaluate_gates, _score_context, reset_scanner_runtime_state

NY_TZ = ZoneInfo("America/New_York")


def _ny_dates() -> tuple[str, str]:
    today = datetime.now(NY_TZ).date()
    prior = today - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    return today.isoformat(), prior.isoformat()


@dataclass(frozen=True)
class _Bar:
    date: str
    close: Optional[float]
    volume: Optional[int]


class _BaseProvider(ScannerDataProvider):
    source_name = "TEST"

    def __init__(self, *, last: float = 110.0, close: Optional[float] = None, volume: int = 150_000, adv20: Optional[int] = 100_000):
        self._last = last
        self._close = close
        self._volume = volume
        self._adv20 = adv20

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int) -> list[str]:
        return ["AAPL"]

    def get_quote(self, symbol: str) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            bid=self._last - 0.5,
            ask=self._last + 0.5,
            last=self._last,
            vwap=self._last - 0.2,
            open=self._last - 2.0,
            high=self._last + 1.0,
            low=self._last - 3.0,
            close=self._close,
            change_percent=None,
            volume=self._volume,
            timestamp_utc="2025-01-01T00:00:00Z",
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return None

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=self._volume,
            current_volume_source_label="TEST",
            average_daily_volume_20d=self._adv20,
            average_daily_volume_window_days=20 if self._adv20 is not None else None,
            relative_volume=3.2 if self._adv20 else None,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        return 10_000_000

    def get_daily_bars(self, identity, lookback_days: int):
        return []


class _DailyBarProvider(_BaseProvider):
    def get_daily_bars(self, identity, lookback_days: int):
        return [_Bar("2025-01-01", 100.0, 120_000)] * 20


class _WeakSnapshotProvider(_BaseProvider):
    pass


class _ProviderPrevCloseFallbackProvider(_BaseProvider):
    def get_daily_bars(self, identity, lookback_days: int):
        return []

    def get_previous_rth_close(self, identity) -> Optional[float]:
        return 101.0


class _SyntheticPctProvider(_BaseProvider):
    def __init__(self):
        super().__init__(last=110.0, close=None, volume=180_000, adv20=120_000)

    def get_daily_bars(self, identity, lookback_days: int):
        return []




class _RetryAwareProvider(_BaseProvider):
    def __init__(self):
        super().__init__(last=110.0, close=None, volume=180_000, adv20=None)
        self.calls = []

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        self.calls.append((use_rth, end_datetime))
        if use_rth:
            return []
        return [_Bar("2025-01-01", 100.0, 120_000)] * 20




class _IdentityPropagationProvider(_BaseProvider):
    source_name = "IBKR"

    def __init__(self):
        super().__init__(last=25.0, close=24.0, volume=220_000, adv20=150_000)
        self.last_scan_details = {"symbol_details": {"AAPL": {"symbol": "AAPL"}}}

    def qualifyContracts(self, *contracts):
        contract = contracts[0]
        contract.conId = 9001
        contract.exchange = "SMART"
        contract.primaryExchange = "NASDAQ"
        contract.tradingClass = "NMS"
        contract.localSymbol = "AAPL"
        contract.currency = "USD"
        return [contract]

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        return [_Bar("2025-01-01", 20.0, 100_000)] * 20


class _HistoryAttemptedNoBarsProvider(_IdentityPropagationProvider):
    def get_quote(self, symbol: str) -> QuoteData:
        return QuoteData(
            symbol=symbol, bid=24.8, ask=25.2, last=25.0, vwap=24.9, open=24.0, high=25.5, low=23.8, close=24.0,
            change_percent=4.2, volume=220_000, timestamp_utc="2025-01-01T00:00:00Z", data_quality_flags=(),
        )

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=None, current_volume_source_label="TEST", average_daily_volume_20d=None, average_daily_volume_window_days=None,
            relative_volume=None, relative_volume_category=None, volume_velocity_5m=None, volume_velocity_15m=None, volume_data_quality_flag="TEST",
        )

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        return []

class _QuoteCloseFallbackProvider(_BaseProvider):
    def __init__(self):
        super().__init__(last=110.0, close=102.0, volume=180_000, adv20=100_000)

    def get_daily_bars(self, identity, lookback_days: int):
        return []


class _TodayAndPriorBarProvider(_BaseProvider):
    def __init__(self):
        super().__init__(last=110.0, close=None, volume=180_000, adv20=100_000)

    def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
        today, prior = _ny_dates()
        return [
            _Bar(prior, 100.0, 120_000),
            _Bar(today, 110.0, 125_000),
        ]


@pytest.fixture(autouse=True)
def _reset_scanner_state() -> None:
    reset_scanner_runtime_state()
    scanner_runner._REFERENCE_RESOLVER.reset_cycle()
    yield
    reset_scanner_runtime_state()
    scanner_runner._REFERENCE_RESOLVER.reset_cycle()


def _thresholds(*, require_catalyst: bool = False) -> GateThresholds:
    return GateThresholds(
        min_price=1.0,
        max_price=500.0,
        min_pct_change=1.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=2.0,
        focus_volume_min=1_000,
        focus_volume_min_early_rth=500,
        focus_volume_min_early_rth_ratio=0.5,
        min_volume=1_000,
        min_premarket_volume=50_000,
        max_float=1_000_000_000,
        spread_max_pct=5.0,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=require_catalyst,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )

def test_pct_change_filters_current_trading_day_partial_bar() -> None:
    provider = _TodayAndPriorBarProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH", {})

    assert context is not None
    assert context["prev_close"] == 100.0
    assert context["pct_change"] == 10.0
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["reference_trading_date"] != datetime.now(NY_TZ).date().isoformat()


def test_reference_resolver_falls_back_when_only_current_day_bar_exists() -> None:
    class _OnlyTodayBarProvider(_BaseProvider):
        def __init__(self):
            super().__init__(last=110.0, close=109.0, volume=180_000, adv20=100_000)

        def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
            today, _ = _ny_dates()
            return [_Bar(today, 110.0, 125_000)]

        def get_previous_rth_close(self, identity) -> Optional[float]:
            return 101.0

    resolver = CanonicalReferenceResolver()
    identity = CandidateIdentity.from_mapping({"symbol": "AAPL"})
    result = resolver.resolve(
        identity=identity,
        provider=_OnlyTodayBarProvider(),
        session_label="RTH",
        current_volume=180_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert result.reference_price == 101.0
    assert result.reference_source == "PROVIDER_PREV_CLOSE_FALLBACK"
    assert result.reference_semantics == "DEGRADED_FALLBACK"


def test_pct_change_fallback_uses_prev_close() -> None:
    provider = _DailyBarProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH", {})

    assert context is not None
    assert context["prev_close"] == 100.0
    assert context["pct_change"] == 10.0
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["reference_quality_tier"] == "PRIMARY"
    assert context["pct_change_qualification_usable"] is True


def test_cached_close_fallback_is_degraded_but_qualification_usable(tmp_path: Path) -> None:
    cache = PersistentReferenceCache(tmp_path / "reference_cache.json")
    provider = _DailyBarProvider()
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
        "localSymbol": "AAPL",
    })

    initial = CanonicalReferenceResolver(cache=cache).resolve(
        identity=identity,
        provider=provider,
        session_label="PRE",
        current_volume=150_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )
    class _BrokenHistoryProvider(_BaseProvider):
        def get_daily_bars(self, identity, lookback_days: int):
            return []

        def get_prev_close(self, symbol: str) -> Optional[float]:
            return None

    second = CanonicalReferenceResolver(cache=cache).resolve(
        identity=identity,
        provider=_BrokenHistoryProvider(),
        session_label="PRE",
        current_volume=150_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert initial.reference_source == "HISTORICAL_LAST_RTH_CLOSE"
    assert second.reference_source == "PERSISTENT_CACHE_PREV_CLOSE"
    assert second.reference_quality_tier == "SECONDARY"
    assert second.reference_semantics == "PREVIOUS_COMPLETED_RTH_CLOSE"
    assert second.reference_is_previous_completed_session is True
    assert second.qualification_usable_reference is True


def test_snapshot_last_price_fallback_is_continuity_only_in_pre() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})

    assert context is not None
    assert context["reference_source"] == "SNAPSHOT_LAST_PRICE_FALLBACK"
    assert context["reference_quality_tier"] == "WEAK"
    assert context["pct_change"] == 0.0
    assert context["pct_change_qualification_usable"] is False
    assert context["watchlist_eligible"] is True
    assert context["execution_eligible"] is False
    assert "PCT_CHANGE_CONTINUITY_ONLY" in context["eligibility_reason_codes"]


def test_rth_zero_bars_recovers_reference_from_provider_prev_close() -> None:
    context = _build_symbol_context(_ProviderPrevCloseFallbackProvider(), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert context["reference_source"] == "PROVIDER_PREV_CLOSE_FALLBACK"
    assert context["reference_quality_tier"] == "SECONDARY"
    assert context["pct_change"] == pytest.approx(8.91, rel=1e-2)
    assert context["reference_semantics"] == "DEGRADED_FALLBACK"
    assert context["pct_change_qualification_usable"] is False
    assert context["pct_change_execution_usable"] is False
    assert context["focus_eligible"] is False
    assert context["reference_price"] == 101.0
    assert context["pct_change_resolved"] == context["pct_change"]
    assert context["gap_pct_resolved"] is not None


def test_rth_zero_bars_recovers_reference_from_quote_close() -> None:
    context = _build_symbol_context(_QuoteCloseFallbackProvider(), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert context["reference_source"] == "QUOTE_CLOSE_FALLBACK"
    assert context["reference_resolved"] is True
    assert context["reference_semantics"] == "DEGRADED_FALLBACK"
    assert context["pct_change_qualification_usable"] is False
    assert context["execution_eligible"] is False
    assert context["pct_change_resolved"] is not None
    assert context["avg_volume_20d"] == 100_000
    assert context["adv20_resolved"] is True
    assert context["rvol_status"] == "RESOLVED"


def test_retry_history_path_allows_smart_primary_exchange_tolerance() -> None:
    provider = _RetryAwareProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH_OPEN", {})

    assert context is not None
    assert len(provider.calls) == 2
    assert provider.calls[0] == (True, "")
    assert provider.calls[1][0] is False
    assert "09:29:59 US/Eastern" in provider.calls[1][1]
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["reference_resolved"] is True
    assert context["reference_price"] == 100.0
    assert context["pct_change_resolved"] == 10.0
    assert context["avg_volume_20d"] == 120_000
    assert context["adv20_resolved"] is True
    assert context["rvol_status"] == "RESOLVED"


def test_trace_toggle_disabled_does_not_emit_targeted_trace(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SCANNER_REFERENCE_TRACE_SYMBOLS", raising=False)

    context = _build_symbol_context(_DailyBarProvider(), "AAPL", "RTH", {})

    assert context is not None
    out = capsys.readouterr().out
    assert "[SCANNER][TRACE]" not in out




def test_qualified_identity_propagates_into_final_context() -> None:
    context = _build_symbol_context(_IdentityPropagationProvider(), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert context["con_id"] == 9001
    assert context["exchange"] == "SMART"
    assert context["primary_exchange"] == "NASDAQ"
    assert context["trading_class"] == "NMS"
    assert context["local_symbol"] == "AAPL"
    assert context["identity_key"] == "conid:9001"


def test_quote_fields_are_preserved_in_final_context() -> None:
    context = _build_symbol_context(_IdentityPropagationProvider(), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert context["last_price"] == 25.0
    assert context["bid"] == 24.5
    assert context["ask"] == 25.5
    assert context["close"] == 24.0
    assert context["volume"] == 220_000
    assert context["ibkr_change_pct"] is None


def test_history_attempted_without_bars_does_not_emit_false_history_or_quote_flags() -> None:
    context = _build_symbol_context(_HistoryAttemptedNoBarsProvider(), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert "HISTORY_DISABLED" not in context["data_quality_flags"]
    assert "CONTRACT_QUALIFY_FAILED" not in context["data_quality_flags"]
    assert "MISSING_LAST" not in context["data_quality_flags"]
    assert "MISSING_CLOSE_TICK" not in context["data_quality_flags"]


def test_verification_script_runs_against_stubbed_live_like_provider(monkeypatch, capsys) -> None:
    from verification_scripts import verify_live_scanner_reference_pipeline as verifier

    monkeypatch.setattr(sys, "argv", ["verify_live_scanner_reference_pipeline.py", "--provider", "stub", "--symbols", "AIM", "ARTL"])
    verifier.main()

    out = capsys.readouterr().out
    assert "A) scanner metadata / identity" in out
    assert "B) direct live quote" in out
    assert "D) direct market_data_client history" in out
    assert "E) resolver" in out
    assert "F) final context" in out
    assert "RESULT: quote_ok=yes" in out


def test_rth_synthetic_pct_reference_is_explicitly_degraded_and_not_execution_usable(tmp_path: Path) -> None:
    provider = _SyntheticPctProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH_OPEN", {})
    assert context is not None
    context["ibkr_change_pct"] = 10.0
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
    })
    result = CanonicalReferenceResolver(cache=PersistentReferenceCache(tmp_path / "synthetic_cache.json")).resolve(
        identity=identity,
        provider=provider,
        session_label="RTH_OPEN",
        current_volume=180_000,
        intraday_avg_volume_20d=120_000,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=109.0,
        ibkr_change_pct=10.0,
        persisted_pct_change=None,
    )
    assert result.reference_source == "SCANNER_PCT_SYNTHETIC_FALLBACK"
    assert result.reference_quality_tier == "DEGRADED_SYNTHETIC"
    assert result.qualification_usable_reference is False
    assert result.execution_usable_reference is False


def test_rth_synthetic_reference_allows_degraded_focus_but_not_execution(tmp_path: Path) -> None:
    provider = _SyntheticPctProvider()
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
    })
    result = CanonicalReferenceResolver(cache=PersistentReferenceCache(tmp_path / "synthetic_focus_cache.json")).resolve(
        identity=identity,
        provider=provider,
        session_label="RTH_OPEN",
        current_volume=180_000,
        intraday_avg_volume_20d=120_000,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=109.0,
        ibkr_change_pct=10.0,
        persisted_pct_change=None,
    )
    context = {
        "session": "RTH_OPEN",
        "symbol": "AAPL",
        "execution_ready": True,
        "reference_quality_tier": "DEGRADED_SYNTHETIC",
        "pct_change_qualification_usable": True,
        "pct_change_execution_usable": False,
        "pct_change_degraded": True,
        "rvol_status": "RESOLVED",
        "adv20_resolved": True,
        "continuity_usable_reference": True,
        "degraded_rvol_gate_bypass": False,
        "eligibility_reason_codes": [],
    }
    scanner_runner._apply_degraded_contract(context)
    assert context["watchlist_eligible"] is True
    assert context["focus_eligible"] is True
    assert context["execution_eligible"] is False
    assert context["execution_ready"] is False
    assert "SYNTHETIC_REFERENCE_DEGRADED" in context["eligibility_reason_codes"]


def test_pre_missing_pct_change_does_not_hard_drop_when_continuity_only() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None

    drop_reason = _evaluate_gates(context, _thresholds())
    assert drop_reason != "DROP_MISSING_PCT_CHANGE"
    assert context["degraded_data_profile"] in {"MULTI_FACTOR_DEGRADED", "UNQUALIFIED_CONTINUITY_ONLY"}


def test_pre_missing_rvol_bypass_requires_strong_anchor() -> None:
    provider = _DailyBarProvider()
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None
    context["rvol"] = None
    context["scanner_rvol"] = None
    context["rvol_phase"] = None
    context["rvol_discovery"] = None
    context["rvol_status"] = "UNKNOWN"
    context["premarket_volume"] = 200_000
    context["volume"] = 200_000
    context["spread_pct"] = 1.0

    assert _evaluate_gates(context, _thresholds()) is None
    assert context["degraded_rvol_gate_bypass"] is True
    assert "PRE_RVOL_BYPASS_APPLIED" in context["eligibility_reason_codes"]


def test_pre_missing_rvol_without_strong_anchor_is_rejected() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None
    context["rvol"] = None
    context["scanner_rvol"] = None
    context["rvol_phase"] = None
    context["rvol_discovery"] = None
    context["rvol_status"] = "UNKNOWN"
    context["premarket_volume"] = 200_000
    context["volume"] = 200_000
    context["spread_pct"] = 1.0

    assert _evaluate_gates(context, _thresholds()) == "DROP_MISSING_RVOL"


def test_fully_qualified_symbol_outranks_degraded_symbol() -> None:
    qualified = _build_symbol_context(_DailyBarProvider(), "AAPL", "PRE", {})
    degraded = _build_symbol_context(_WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None), "MSFT", "PRE", {})
    assert qualified is not None and degraded is not None

    qualified_score, _ = _score_context(qualified)
    degraded_score, _ = _score_context(degraded)

    assert qualified_score > degraded_score
    assert degraded["execution_eligible"] is False


def test_unresolved_reference_cannot_remain_execution_ready() -> None:
    context = _build_symbol_context(_WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None), "AAPL", "RTH_OPEN", {})
    assert context is not None
    assert context["reference_source"] == "UNRESOLVED" or context["execution_eligible"] is False
    assert context["execution_ready"] is False


def test_rth_mid_zero_bars_retries_with_use_rth_false_and_recovers_reference() -> None:
    provider = _RetryAwareProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH_MID", {})

    assert context is not None
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["pct_change"] == 10.0
    assert provider.calls[0] == (True, "")
    assert provider.calls[1][0] is False
    assert provider.calls[1][1].endswith("US/Eastern")

def test_rth_history_qualification_does_not_fail_when_primary_exchange_is_smart() -> None:
    class _QualifiedSmartProvider(_RetryAwareProvider):
        source_name = "IBKR"

        def get_daily_bars(self, identity, lookback_days: int, *, use_rth: bool = True, end_datetime: str = ""):
            return super().get_daily_bars(identity, lookback_days, use_rth=use_rth, end_datetime=end_datetime)

        def qualifyContracts(self, contract):
            contract.conId = 12345
            contract.exchange = "SMART"
            contract.primaryExchange = "SMART"
            return [contract]

    context = _build_symbol_context(_QualifiedSmartProvider(), "AAPL", "RTH_MID", {})

    assert context is not None
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["pct_change_resolved"] == 10.0


def test_rth_mid_excludes_current_day_daily_bar_for_previous_close() -> None:
    provider = _TodayAndPriorBarProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH_MID", {})

    today, prior = _ny_dates()
    assert context is not None
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["reference_price"] == 100.0
    assert context["reference_trading_date"] == prior
    assert context["reference_semantics"] == "PREVIOUS_COMPLETED_RTH_CLOSE"
    assert context["reference_is_previous_completed_session"] is True
    assert context["reference_trading_date"] != today
    assert context["pct_change_resolved"] == 10.0


def test_cached_reference_equal_to_current_last_in_rth_is_degraded_and_not_qualification_usable(tmp_path: Path) -> None:
    today, _ = _ny_dates()
    cache = PersistentReferenceCache(tmp_path / "reference_cache.json")
    cache.put(("conid:101",), {
        "identity_key": "conid:101",
        "symbol": "AAPL",
        "reference_price": 110.0,
        "reference_label": "LAST_RTH_CLOSE",
        "reference_source": "HISTORICAL_LAST_RTH_CLOSE",
        "reference_resolved": True,
        "reference_semantics": "CURRENT_SESSION_CLOSE",
        "reference_trading_date": today,
        "reference_is_previous_completed_session": False,
        "asof_trading_date": today,
        "cache_trading_date": today,
        "avg_volume_20d": 100000,
        "average_daily_volume_window_days": 20,
        "adv20_source": "HISTORICAL_LAST_RTH_CLOSE",
        "adv20_resolved": True,
    })
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
        "localSymbol": "AAPL",
    })

    class _CacheOnlyProvider(_BaseProvider):
        def get_daily_bars(self, identity, lookback_days: int):
            return []

        def get_prev_close(self, symbol: str) -> Optional[float]:
            return None

    result = CanonicalReferenceResolver(cache=cache).resolve(
        identity=identity,
        provider=_CacheOnlyProvider(last=110.0),
        session_label="RTH_MID",
        current_volume=150_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert result.reference_source == "PERSISTENT_CACHE_PREV_CLOSE"
    assert result.reference_semantics == "CURRENT_SESSION_CLOSE"
    assert result.reference_is_previous_completed_session is False
    assert result.reference_degraded is True
    assert result.qualification_usable_reference is False
    assert result.execution_usable_reference is False


def test_current_day_partial_bar_is_not_selected_as_last_rth_close() -> None:
    provider = _TodayAndPriorBarProvider()
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
    })

    result = CanonicalReferenceResolver(cache=PersistentReferenceCache(Path("/tmp/nonpersistent_reference_cache.json"))).resolve(
        identity=identity,
        provider=provider,
        session_label="RTH_OPEN",
        current_volume=180_000,
        intraday_avg_volume_20d=100_000,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert result.reference_price == 100.0
    assert result.reference_semantics == "PREVIOUS_COMPLETED_RTH_CLOSE"
    assert result.reference_is_previous_completed_session is True
    assert result.reference_trading_date != _ny_dates()[0]


def test_closed_session_pct_change_uses_last_rth_close_reference() -> None:
    context = _build_symbol_context(_DailyBarProvider(), "AAPL", "CLOSED", {})
    assert context is not None
    assert context["reference_source"] == "HISTORICAL_LAST_RTH_CLOSE"
    assert context["reference_price"] == 100.0
    assert context["pct_change"] == 10.0


def test_closed_session_rvol_uses_explicit_prep_fallback() -> None:
    context = _build_symbol_context(_DailyBarProvider(volume=50_000, adv20=1_000_000), "AAPL", "CLOSED", {})
    assert context is not None
    assert context["rvol_method"] == "PREP_PHASE_FALLBACK"
    assert context["expected_phase_volume"] == 50_000.0
    assert context["rvol"] == 1.0


def test_reference_missing_is_explicit_hard_fail_when_no_fallback_exists() -> None:
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
    })
    result = CanonicalReferenceResolver(cache=PersistentReferenceCache(Path('/tmp/reference_missing_hard_fail.json'))).resolve(
        identity=identity,
        provider=_WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None),
        session_label="RTH_OPEN",
        current_volume=180_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )
    assert result.reference_source == "REFERENCE_MISSING_HARD_FAIL"
    assert result.reference_failure_reason == "REFERENCE_MISSING_HARD_FAIL"


def test_pre_symbol_survives_pct_gate_with_historical_reference() -> None:
    context = _build_symbol_context(_DailyBarProvider(), "AAPL", "PRE", {})
    assert context is not None
    assert context["pct_change"] == 10.0
    assert _evaluate_gates(context, _thresholds()) is None
