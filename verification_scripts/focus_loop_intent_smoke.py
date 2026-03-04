from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.config.runtime_config import RunMode
from src.strategy.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def main() -> int:
    strategy = RossMomentumStrategyV1()
    intents = strategy.process_watchlist(
        watchlist=[{'symbol': 'AAPL'}],
        snapshots={},
        session_label='RTH',
        timestamp_utc='2026-01-01T14:30:00+00:00',
        mode=RunMode.PAPER,
        session_phase='OPENING_0_30',
    )
    assert intents, 'Expected at least one TRADE_INTENT'
    print(f'focus_loop_intent_smoke=PASS intents={len(intents)} symbol={intents[0].symbol}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
