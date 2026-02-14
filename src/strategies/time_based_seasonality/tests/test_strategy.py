from src.config.runtime_config import RunMode
from src.strategies.time_based_seasonality.strategy import TimeBasedSeasonalityStrategy


def test_bucket_window_can_trade() -> None:
    strategy = TimeBasedSeasonalityStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T01:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert len(intents) == 1


def test_outside_bucket_no_trade() -> None:
    strategy = TimeBasedSeasonalityStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T03:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert intents == []
