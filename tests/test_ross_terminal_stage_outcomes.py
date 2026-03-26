from __future__ import annotations

from src.config.runtime_config import RunMode
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def test_ross_emits_terminal_stage_for_context_rejection(monkeypatch, capsys) -> None:
    strategy = RossMomentumStrategyV1()
    monkeypatch.setattr(
        "src.strategies.ross_momentum_strategy_v1.build_runtime_pattern_inputs",
        lambda **_: (None, ["MISSING_REQUIRED_FIELDS"]),
    )
    strategy.process_watchlist(
        watchlist=[{"symbol": "TEST"}],
        snapshots={},
        session_label="PRE",
        timestamp_utc="2026-03-26T12:00:00+00:00",
        mode=RunMode.PAPER,
        session_phase="PRE",
        session_contract={"canonical_session": "PRE"},
    )
    out = capsys.readouterr().out
    assert "[ROSS][TERMINAL_STAGE] symbol=TEST outcome=CONTEXT_REJECTED" in out
