"""Smoke test for Ross focus-loop intent generation surface."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.runtime_config import RunMode
from src.strategy.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def main() -> int:
    strategy = RossMomentumStrategyV1()
    intents = strategy.process_watchlist(
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="RTH",
        timestamp_utc="2026-01-01T14:30:00Z",
        mode=RunMode.SIM,
        session_phase="OPENING_DRIVE",
    )

    assert isinstance(intents, list), "process_watchlist must return a list"
    print(f"PASS: focus_loop_intent_smoke intents_count={len(intents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
