from src.config.runtime_config import RunMode
from src.strategies.trend_following_classic.strategy import TrendFollowingClassicStrategy


def test_trend_outputs_at_most_one_intent() -> None:
    strategy = TrendFollowingClassicStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}, {"symbol": "MSFT"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert len(intents) <= 1


def test_read_only_returns_empty() -> None:
    strategy = TrendFollowingClassicStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.READ_ONLY,
        session_phase="MORNING",
    )
    assert intents == []
