from __future__ import annotations

from datetime import date, datetime, timezone

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import get_ibkr_readonly_enabled
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.reference_resolver import CanonicalReferenceResolver, PersistentReferenceCache
from src.scanner.session_pct_change import (
    compute_session_aligned_pct_change,
    resolve_market_session_context,
    resolve_session_diagnostics,
)
from src.strategy.strategy_runner import StrategyRunner


class _Bar:
    def __init__(self, trading_date: str, close: float, volume: int = 100_000) -> None:
        self.date = trading_date
        self.close = close
        self.volume = volume


class _Provider:
    source_name = "IBKR"

    def __init__(self, *, bars: list[_Bar] | None = None, quote_close: float | None = None) -> None:
        self.bars = bars or []
        self.quote_close = quote_close
        self.qualify_calls = 0
        self.history_calls = 0

    def qualifyContracts(self, contract):
        self.qualify_calls += 1
        contract.conId = 1234
        contract.primaryExchange = "NASDAQ"
        contract.exchange = "SMART"
        return [contract]

    def get_daily_bars(self, identity, lookback_days: int):
        self.history_calls += 1
        return list(self.bars)

    def get_quote(self, symbol: str):
        class Quote:
            close = self.quote_close

        return Quote()


def test_weekday_overnight_is_closed_not_weekend() -> None:
    probe = datetime(2026, 3, 19, 0, 20, tzinfo=timezone.utc)
    context = resolve_market_session_context(probe)
    diagnostics = resolve_session_diagnostics(probe)

    assert context.phase == "OVN"
    assert diagnostics.resolved_session == "OVN"
    assert diagnostics.canonical_session == "CLOSED"


def test_true_weekend_remains_weekend() -> None:
    probe = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    context = resolve_market_session_context(probe)
    diagnostics = resolve_session_diagnostics(probe)

    assert context.phase == "WEEKEND"
    assert diagnostics.resolved_session == "WEEKEND"
    assert diagnostics.canonical_session == "CLOSED"


def test_holiday_is_closed_not_weekend() -> None:
    set_config_overrides({"MARKET_HOLIDAYS": {date(2026, 1, 1)}})
    try:
        diagnostics = resolve_session_diagnostics(datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc))
    finally:
        set_config_overrides(None)

    assert diagnostics.resolved_session == "CLOSED"
    assert diagnostics.canonical_session == "CLOSED"


def test_closed_session_pct_change_uses_last_rth_reference() -> None:
    payload = compute_session_aligned_pct_change(
        session_label="CLOSED",
        cur_last=1.74,
        ref_close_rth=1.20,
        rth_open_price=None,
        rth_close_price=1.20,
        ibkr_change_pct=None,
    )

    assert payload.reference_price == 1.20
    assert payload.final_pct == 45.0


def test_snapshot_close_fallback_resolves_reference_and_pct(tmp_path) -> None:
    resolver = CanonicalReferenceResolver(PersistentReferenceCache(tmp_path / "reference_cache.json"))
    provider = _Provider(bars=[], quote_close=None)
    result = resolver.resolve(
        identity=CandidateIdentity(symbol="MDAI", con_id=1234, exchange="SMART", primary_exchange="NASDAQ"),
        provider=provider,
        session_label="CLOSED",
        current_volume=780,
        intraday_avg_volume_20d=None,
        current_last_price=1.74,
        rth_open_price=None,
        rth_close_price=1.20,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert result.reference_source == "SNAPSHOT_CLOSE_FALLBACK"
    assert result.reference_price == 1.20


def test_history_reference_requests_are_memoized_within_cycle() -> None:
    resolver = CanonicalReferenceResolver()
    provider = _Provider(bars=[_Bar("2026-03-18", 10.0)])
    identity = CandidateIdentity(symbol="TEST", exchange="SMART", primary_exchange="NASDAQ")

    first = resolver.resolve(
        identity=identity,
        provider=provider,
        session_label="CLOSED",
        current_volume=100,
        intraday_avg_volume_20d=None,
        current_last_price=11.0,
        rth_open_price=None,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )
    second = resolver.resolve(
        identity=CandidateIdentity(symbol="TEST", exchange="SMART", primary_exchange="NASDAQ"),
        provider=provider,
        session_label="CLOSED",
        current_volume=100,
        intraday_avg_volume_20d=None,
        current_last_price=11.0,
        rth_open_price=None,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert first.reference_price == second.reference_price == 10.0
    assert provider.qualify_calls == 1
    assert provider.history_calls == 1


def test_live_writable_runtime_is_not_forced_readonly() -> None:
    set_config_overrides(
        {
            "RUN_MODE": "LIVE",
            "EXECUTION_ENABLED": True,
            "IBKR_READONLY_ENABLED": False,
            "IBKR_API_WRITE_ALLOWED": True,
        }
    )
    try:
        assert get_ibkr_readonly_enabled() is False
    finally:
        set_config_overrides(None)


def test_strategy_runner_live_defaults_exclude_legacy_gap_and_go_noise() -> None:
    set_config_overrides(
        {
            "SELECTED_STRATEGY": "",
            "RUN_MODE": "LIVE",
            "ENABLED_STRATEGIES": {
                "GapAndGoStrategy": False,
                "MomentumContinuationStrategy": False,
            },
            "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": False,
            "MEAN_REVERSION_STRATEGY_ENABLED": False,
            "LONG_HORIZON_VALUE_STRATEGY_ENABLED": False,
        }
    )
    try:
        runner = StrategyRunner()
    finally:
        set_config_overrides(None)

    assert all(strategy.name not in {"GapAndGoStrategy", "MomentumContinuationStrategy"} for strategy in runner.strategies)
