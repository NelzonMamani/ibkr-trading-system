from src.config.runtime_config import RunMode
from src.scanner.result_models import CandidateMetrics
from src.strategies.opening_drive.strategy import OpeningDriveStrategy


def _candidate(symbol: str, *, strong: bool = False) -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol, con_id=None, exchange="NASDAQ", session_label="REG",
        last_price=10.3 if strong else 10.0, prev_close=9.8, ref_close_rth=9.8, reference_price=9.8,
        reference_label="RTH", gap_pct=4.0 if strong else 0.4, pct_change=4.0 if strong else 0.4,
        ibkr_change_pct=4.0 if strong else 0.4, pct_source="SESSION", rvol=2.0 if strong else 0.8,
        relative_volume=2.0 if strong else 0.8, avg_volume_20d=1000000, float_shares=10000000,
        float_millions=10.0, volume=1500000, premarket_volume=200000, dollar_volume=15000000.0,
        bid=9.99, ask=10.01, spread=0.02, spread_pct=0.002, halted=False, ssr=False,
        catalyst_present=True, catalyst_summary="news", data_quality_ok=True
    )


def test_opening_drive_determinism_and_contract() -> None:
    strategy = OpeningDriveStrategy()
    kwargs = dict(
        watchlist=[_candidate("AAPL", strong=True)],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T14:31:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert [i.symbol for i in first] == ["AAPL"]
    assert [(i.symbol, i.direction, i.strategy_name) for i in first] == [
        (i.symbol, i.direction, i.strategy_name) for i in second
    ]


def test_opening_drive_fallback_long_only_in_sim_paper() -> None:
    strategy = OpeningDriveStrategy()
    kwargs = dict(
        watchlist=[_candidate("AAPL", strong=False)], snapshots={}, session_label="REG",
        timestamp_utc="2026-02-14T14:31:00+00:00", session_phase="MORNING",
    )
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.SIM, **kwargs))
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.PAPER, **kwargs))
