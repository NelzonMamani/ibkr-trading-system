from dataclasses import dataclass


@dataclass(frozen=True)
class TimePolicy:
    max_hold_time_seconds: int = 300
    weak_trade_pnl_threshold: float = 0.0
    close_before_session_end_seconds: int = 60
