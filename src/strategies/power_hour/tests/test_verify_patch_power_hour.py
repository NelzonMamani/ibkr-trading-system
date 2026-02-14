from src.config.runtime_config import RunMode
from src.strategies.power_hour.strategy import PowerHourStrategy


def test_power_hour_determinism_and_contract() -> None:
    strategy = PowerHourStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.5, "hod": 10.45, "rvol": 1.6}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T19:05:00+00:00",
        mode=RunMode.LIVE,
        session_phase="POWER_HOUR",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert len(first) == 1
    assert first[0].symbol == "AAPL"
    assert [(i.symbol, i.direction) for i in first] == [(i.symbol, i.direction) for i in second]


def test_power_hour_fallback_long_only_in_sim_paper() -> None:
    strategy = PowerHourStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.0, "hod": 10.6, "rvol": 0.9}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T18:00:00+00:00",
        session_phase="MORNING",
    )
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.SIM, **kwargs))
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.PAPER, **kwargs))
