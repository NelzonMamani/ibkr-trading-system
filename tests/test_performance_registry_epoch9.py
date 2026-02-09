from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from core.events import SystemEvent
from core.performance_registry import PerformanceRegistry


def test_performance_registry_snapshot_metrics_and_ordering():
    registry = PerformanceRegistry()
    events = [
        SystemEvent(
            event_type="TRADE_CLOSED",
            source="TEST",
            timestamp=datetime(2024, 1, 2, 12, 0, 0),
            payload={
                "symbol": "BBB",
                "trader_type": "MANUAL",
                "strategy_name": "ALPHA",
                "pattern_name": "PATTERN_A",
                "gross_realised_pnl": 100.0,
                "commission": 2.0,
                "net_realised_pnl": 98.0,
                "entry_price": 100.0,
                "exit_price": 110.0,
                "quantity": 1,
                "stop_loss_price": 95.0,
                "direction": "LONG",
                "exit_category": "EXIT_TARGET",
                "exit_reason": "TAKE_PROFIT",
            },
        ),
        SystemEvent(
            event_type="TRADE_CLOSED",
            source="TEST",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            payload={
                "symbol": "AAA",
                "trader_type": "MANUAL",
                "strategy_name": "ALPHA",
                "pattern_name": "PATTERN_A",
                "gross_realised_pnl": -50.0,
                "commission": 1.0,
                "net_realised_pnl": -51.0,
                "entry_price": 200.0,
                "exit_price": 190.0,
                "quantity": 1,
                "stop_loss_price": 180.0,
                "direction": "LONG",
                "exit_category": "EXIT_STOP_LOSS",
                "exit_reason": "STOP_LOSS",
            },
        ),
    ]

    registry.record(events)
    snapshot = registry.snapshot()

    assert snapshot.total_trades == 2
    assert snapshot.wins == 1
    assert snapshot.losses == 1
    assert snapshot.flats == 0
    assert snapshot.gross_pnl == pytest.approx(50.0)
    assert snapshot.total_commissions == pytest.approx(3.0)
    assert snapshot.net_pnl == pytest.approx(47.0)
    assert snapshot.avg_pnl_per_trade == pytest.approx(23.5)
    assert snapshot.win_rate == pytest.approx(0.5)

    strategy_bucket = snapshot.by_strategy["ALPHA"]
    assert strategy_bucket["total_trades"] == 2
    assert strategy_bucket["net_pnl"] == pytest.approx(47.0)
    assert strategy_bucket["avg_pnl_per_trade"] == pytest.approx(23.5)

    outcomes = snapshot.trade_outcomes
    assert outcomes[0]["symbol"] == "AAA"
    assert outcomes[1]["symbol"] == "BBB"
