from src.config.runtime_config import RunMode
from src.strategies.opening_drive.strategy import OpeningDriveStrategy
from src.strategies.opening_drive.strategy_policy import POLICY


def test_policy_modes_are_safely_gated() -> None:
    assert RunMode.LIVE not in POLICY.allowed_modes_for_intents
    assert RunMode.READ_ONLY not in POLICY.allowed_modes_for_intents


def test_deterministic_intent_in_sim_with_watchlist() -> None:
    strategy = OpeningDriveStrategy()
    kwargs = dict(
        watchlist=[{"symbol": "AAPL", "last": 190.0, "volume": 5_000_000}],
        snapshots={},
        session_label=POLICY.allowed_sessions[0],
        timestamp_utc="2026-02-14T14:55:00+00:00",
        mode=RunMode.SIM,
        session_phase="MORNING",
    )
    first = strategy.process_watchlist(**kwargs)
    second = strategy.process_watchlist(**kwargs)
    assert len(first) == 1
    assert first == second
    assert first[0].pattern_name == f"{POLICY.name.upper()}_DETERMINISTIC_FALLBACK"


def test_live_mode_emits_no_intents() -> None:
    strategy = OpeningDriveStrategy()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL", "last": 190.0, "volume": 5_000_000}],
        snapshots={},
        session_label=POLICY.allowed_sessions[0],
        timestamp_utc="2026-02-14T14:55:00+00:00",
        mode=RunMode.LIVE,
        session_phase="MORNING",
    )
    assert intents == []
