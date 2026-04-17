from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPolicy:
    stop_offset_pct: float = 0.01
