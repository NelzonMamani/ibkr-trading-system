from dataclasses import dataclass


@dataclass(frozen=True)
class TrailingPolicy:
    early_session_anchor: str = "higher_low_1m"
    late_session_anchor: str = "higher_low_5m"
    late_session_min_hold_seconds: int = 900
