from src.config.runtime_config import RunMode
from src.strategies.vwap_reclaim.strategy import VwapReclaimStrategy


def test_vwap_reclaim_determinism_and_contract() -> None:
    strategy = VwapReclaimStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.2, "vwap": 10.0, "vwap_hold_minutes": 3, "rvol": 1.5}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert len(first) == 1
    assert first[0].symbol == "AAPL"
    assert first[0].strategy_name == "VwapReclaimStrategy"
    assert [(i.symbol, i.direction) for i in first] == [(i.symbol, i.direction) for i in second]


def test_vwap_reclaim_fallback_long_only_in_sim_paper() -> None:
    strategy = VwapReclaimStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 9.8, "vwap": 10.0, "vwap_hold_minutes": 0, "rvol": 0.8}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        session_phase="MORNING",
    )
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.SIM, **kwargs))
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.PAPER, **kwargs))
