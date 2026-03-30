from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GlobalKillSwitch:
    active: bool = False
    reason: str = ""

    def activate(self, reason: str) -> None:
        normalized = str(reason or "unspecified")
        if not self.active or self.reason != normalized:
            print(f"[LIFECYCLE][KILL_SWITCH] activated reason={normalized}")
        self.active = True
        self.reason = normalized

    def deactivate(self) -> None:
        self.active = False
        self.reason = ""
