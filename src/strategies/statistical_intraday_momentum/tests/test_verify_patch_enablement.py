from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.strategy.strategy_runner import StrategyRunner
from src.scanner.result_models import CandidateMetrics
from src.strategies.statistical_intraday_momentum.strategy import StatisticalIntradayMomentum


def _candidate(symbol: str) -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol, con_id=None, exchange="NASDAQ", session_label="REG",
        session_phase="REG",
        last_price=10.0, prev_close=9.5, ref_close_rth=9.5, reference_price=9.5,
        reference_label="RTH", reference_source="TEST", reference_quality_tier="PRIMARY", reference_resolved=True,
        gap_pct=5.0, pct_change=5.0, pct_change_resolved=5.0, pct_change_qualification_usable=True,
        pct_change_execution_usable=True, pct_change_source_quality="PRIMARY", pct_change_degraded=False,
        pct_change_synthetic=False, pct_change_failure_reason=None, gap_pct_resolved=5.0, gap_source="SESSION",
        context_status="LIVE", execution_ready=True, prep_only=False, live_rvol_deferred=False, prep_seeded=False,
        live_confirmation_pending=False, watchlist_source="TEST", promotion_reason="TEST", ibkr_change_pct=5.0,
        pct_source="SESSION", open_relative_pct_change=None, hod_pct=None, rvol=2.5, rvol_discovery=2.5, rvol_phase=2.5,
        phase_volume_ratio=1.0, relative_volume=2.5, avg_volume_20d=1000000, adv20_resolved=True, degraded_adv20=False,
        adv20_source="TEST", rvol_status="RESOLVED", rvol_failure_reason=None, rvol_degraded=False,
        rvol_qualification_usable=True, rvol_execution_usable=True, degraded_rvol_gate_bypass=False,
        float_shares=10000000, float_source="TEST", float_asof="2026-01-01T00:00:00+00:00", float_cache_hit=True,
        float_millions=10.0, volume=1200000, premarket_volume=100000,
        dollar_volume=12000000.0, bid=9.99, ask=10.01, spread=0.02, spread_pct=0.002,
        halted=False, ssr=False, catalyst_present=True, catalyst_summary="news", news_count=1, fresh_news_count=1,
        stale_news_count=0, top_news_title="news", top_news_age_hours=0.1, top_news_catalyst_tag="NEWS",
        news_source_mode="TEST", news_asof="2026-01-01T00:00:00+00:00", data_quality_ok=True
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


def test_statistical_intents_are_long_only_in_sim_and_paper() -> None:
    strategy = StatisticalIntradayMomentum()
    watchlist = [_candidate("AAPL")]
    kwargs = dict(
        watchlist=watchlist,
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:40:00+00:00",
        session_phase="MORNING",
    )

    sim_intents = strategy.process_watchlist(mode=RunMode.SIM, **kwargs)
    paper_intents = strategy.process_watchlist(mode=RunMode.PAPER, **kwargs)

    assert all(intent.direction == "LONG" for intent in sim_intents)
    assert all(intent.direction == "LONG" for intent in paper_intents)


def test_statistical_watchlist_accepts_dict_rows_without_crashing() -> None:
    strategy = StatisticalIntradayMomentum()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:40:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert isinstance(intents, list)
