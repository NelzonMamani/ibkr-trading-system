from dataclasses import dataclass


@dataclass(frozen=True)
class TargetPolicy:
    target1_r_multiple: float = 1.0
    target1_exit_fraction: float = 0.5
    target2_enabled: bool = True
    target2_r_multiple: float = 2.0
