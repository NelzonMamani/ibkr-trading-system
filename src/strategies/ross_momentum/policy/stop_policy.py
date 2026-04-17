from dataclasses import dataclass


@dataclass(frozen=True)
class StopPolicy:
    stop_offset_pct: float = 0.01
    break_even_buffer_pct: float = 0.0
