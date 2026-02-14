from src.config.runtime_config import RunMode
from src.strategies.event_news_shock_continuation.strategy import EventNewsShockContinuationStrategy


def _entry(**overrides):
    base = {"symbol": "AAPL"}
    base.update({'news_score': 0.8, 'pct_change': 4.0, 'relative_volume': 2.0})
    base.update(overrides)
    return base


def test_strategy_generates_intent_in_sim() -> None:
    strategy = EventNewsShockContinuationStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert len(intents) == 1


def test_strategy_generates_intent_in_paper() -> None:
    strategy = EventNewsShockContinuationStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="MORNING",
    )
    assert len(intents) == 1


def test_strategy_returns_empty_in_live() -> None:
    strategy = EventNewsShockContinuationStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry(symbol="")],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    assert intents == []


def test_strategy_handles_dict_watchlist_rows() -> None:
    strategy = EventNewsShockContinuationStrategy()
    intents = strategy.process_watchlist(
        watchlist=[_entry()],
        snapshots={},
        session_label="REG",
        timestamp_utc="2026-02-14T15:00:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    assert intents and intents[0].symbol == "AAPL"
