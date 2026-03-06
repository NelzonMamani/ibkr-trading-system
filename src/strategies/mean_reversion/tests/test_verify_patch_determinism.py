from src.config.runtime_config import RunMode
from src.scanner.result_models import CandidateMetrics
from src.strategies.mean_reversion.mean_reversion_strategy_policy import MeanReversionPolicyConfig
from src.strategies.mean_reversion.strategy import MeanReversionStrategy


def _candidate(symbol: str) -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol,
        con_id=None,
        exchange="NASDAQ",
        session_label="REG",
        last_price=10.0,
        prev_close=9.5,
        ref_close_rth=9.5,
        reference_price=9.5,
        reference_label="RTH",
        gap_pct=5.0,
        pct_change=5.0,
        ibkr_change_pct=5.0,
        pct_source="SESSION",
        open_relative_pct_change=5.0,
        rvol=2.0,
        relative_volume=2.0,
        avg_volume_20d=1000000,
        float_shares=10000000,
        float_millions=10.0,
        volume=1200000,
        premarket_volume=200000,
        dollar_volume=12000000.0,
        bid=9.99,
        ask=10.01,
        spread=0.02,
        spread_pct=0.002,
        halted=False,
        ssr=False,
        catalyst_present=False,
        catalyst_summary=None,
        data_quality_ok=True,
    )


def test_mean_reversion_policy_parameters_load() -> None:
    cfg = MeanReversionPolicyConfig()
    assert cfg.primary_mean == "VWAP"
    assert cfg.min_rr >= 1.0
    assert cfg.max_trades_per_symbol_per_day >= 1


def test_mean_reversion_watchlist_processing_is_deterministic() -> None:
    strategy = MeanReversionStrategy()
    watchlist = [_candidate("AAPL")]
    kwargs = dict(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:45:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )

    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert [intent.symbol for intent in first] == [intent.symbol for intent in second]


def test_mean_reversion_handles_empty_watchlist() -> None:
    strategy = MeanReversionStrategy()
    intents = strategy.process_watchlist(
        watchlist=[],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:45:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert intents == []


def test_mean_reversion_fallback_is_long_only_in_sim_and_paper() -> None:
    strategy = MeanReversionStrategy()
    watchlist = [_candidate("AAPL")]

    for mode in (RunMode.SIM, RunMode.PAPER):
        intents = strategy.process_watchlist(
            watchlist=watchlist,
            snapshots={},
            session_label="REG",
            timestamp_utc="2026-02-14T14:45:00+00:00",
            mode=mode,
            session_phase="MORNING",
        )
        assert all(intent.direction == "LONG" for intent in intents)
