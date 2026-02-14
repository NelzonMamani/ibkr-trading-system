from src.config.runtime_config import RunMode
from src.strategies.volatility_expansion.strategy import VolatilityExpansionStrategy


def test_volatility_expansion_determinism_and_contract() -> None:
    strategy = VolatilityExpansionStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.3, "opening_range_high": 10.2, "opening_range_low": 9.8, "consolidation_range_pct": 2.0, "rvol": 1.5}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T16:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="AFTERNOON",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert len(first) == 1
    assert first[0].symbol == "AAPL"
    assert [(i.symbol, i.direction) for i in first] == [(i.symbol, i.direction) for i in second]


def test_volatility_expansion_fallback_long_only_in_sim_paper() -> None:
    strategy = VolatilityExpansionStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last_price": 10.0, "opening_range_high": 10.2, "opening_range_low": 9.8, "consolidation_range_pct": 5.0, "rvol": 0.9}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T16:00:00+00:00",
        session_phase="AFTERNOON",
    )
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.SIM, **kwargs))
    assert all(i.direction == "LONG" for i in strategy.process_watchlist(mode=RunMode.PAPER, **kwargs))
