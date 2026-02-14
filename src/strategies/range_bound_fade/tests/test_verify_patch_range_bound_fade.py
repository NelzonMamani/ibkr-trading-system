from src.config.runtime_config import RunMode
from src.strategies.range_bound_fade.strategy import RangeBoundFadeStrategy


def test_range_bound_fade_determinism_and_contract() -> None:
    strategy = RangeBoundFadeStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 9.85, "opening_range_high": 10.5, "opening_range_low": 9.8}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T16:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert len(first) == 1
    assert first[0].symbol == "AAPL"
    assert [(i.symbol, i.direction) for i in first] == [(i.symbol, i.direction) for i in second]


def test_range_bound_fade_fallback_long_only_in_sim_paper() -> None:
    strategy = RangeBoundFadeStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.4, "opening_range_high": 10.5, "opening_range_low": 9.8}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T16:00:00+00:00",
        session_phase="MORNING",
    )
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.SIM, **kwargs))
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.PAPER, **kwargs))
