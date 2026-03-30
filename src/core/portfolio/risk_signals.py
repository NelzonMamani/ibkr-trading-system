from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LifecycleRiskSignals:
    max_drawdown_breached: bool = False
    pnl_drop_rate_exceeded: bool = False
    too_many_open_positions: bool = False
    drift_detected: bool = False
