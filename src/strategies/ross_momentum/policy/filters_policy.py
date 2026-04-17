from dataclasses import dataclass


@dataclass(frozen=True)
class FiltersPolicy:
    require_in_play: bool = True
