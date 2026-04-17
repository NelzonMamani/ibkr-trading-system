from dataclasses import dataclass


@dataclass(frozen=True)
class EntryPolicy:
    allow_reentry: bool = True
