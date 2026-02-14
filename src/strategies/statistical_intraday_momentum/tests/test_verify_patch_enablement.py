from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.strategy.strategy_runner import StrategyRunner
from src.scanner.result_models import CandidateMetrics
from src.strategies.statistical_intraday_momentum.strategy import StatisticalIntradayMomentum


def _candidate(symbol: str) -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol, con_id=None, exchange="NASDAQ", session_label="REG",
        last_price=10.0, prev_close=9.5, ref_close_rth=9.5, reference_price=9.5,
        reference_label="RTH", gap_pct=5.0, pct_change=5.0, ibkr_change_pct=5.0,
        pct_source="SESSION", rvol=2.5, relative_volume=2.5, avg_volume_20d=1000000,
        float_shares=10000000, float_millions=10.0, volume=1200000, premarket_volume=100000,
        dollar_volume=12000000.0, bid=9.99, ask=10.01, spread=0.02, spread_pct=0.002,
        halted=False, ssr=False, catalyst_present=True, catalyst_summary="news", data_quality_ok=True
    )


def test_statistical_strategy_enablement_and_registration() -> None:
    set_config_overrides(
        {
            "SELECTED_STRATEGY": "statistical_intraday_momentum",
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": True,
        }
    )
    try:
        runner = StrategyRunner()
    finally:
        set_config_overrides({})

    assert len(runner.strategies) == 1
    assert isinstance(runner.strategies[0], StatisticalIntradayMomentum)


def test_statistical_watchlist_handler_safe_noop_for_empty_watchlist() -> None:
    strategy = StatisticalIntradayMomentum()
    intents = strategy.process_watchlist(
        watchlist=[],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:35:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert intents == []


def test_statistical_watchlist_processing_is_deterministic() -> None:
    strategy = StatisticalIntradayMomentum()
    watchlist = [_candidate("AAPL"), _candidate("MSFT")]
    kwargs = dict(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:40:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )

    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert [intent.symbol for intent in first] == [intent.symbol for intent in second]
