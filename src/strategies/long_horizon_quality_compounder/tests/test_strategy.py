from src.config.runtime_config import RunMode
from src.strategies.long_horizon_quality_compounder.strategy import (
    LongHorizonQualityCompounderStrategy,
)


def test_quality_deterministic_thresholding() -> None:
    strategy = LongHorizonQualityCompounderStrategy()
    intents_first = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    intents_second = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert [i.symbol for i in intents_first] == [i.symbol for i in intents_second]


def test_empty_watchlist_safe() -> None:
    strategy = LongHorizonQualityCompounderStrategy()
    assert strategy.process_watchlist(
        watchlist=[],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    ) == []
