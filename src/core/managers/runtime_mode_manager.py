from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import get_config
from src.config.runtime_config import EventReplayMode, RunMode


@dataclass(frozen=True)
class RuntimeModeManager:
    resolved_mode: RunMode
    is_live_like: bool
    allow_orders: bool
    max_shares_per_order: int | None
    event_replay_mode: EventReplayMode

    @classmethod
    def resolve(cls) -> "RuntimeModeManager":
        resolved_mode = RunMode(get_config("RUN_MODE_EFFECTIVE"))
        event_replay_mode = EventReplayMode(get_config("EVENT_REPLAY_MODE_EFFECTIVE"))
        is_live_like = resolved_mode in {
            RunMode.LIVE,
            RunMode.LIVE_ONE_SHARE,
            RunMode.LIVE_MICRO,
        }
        allow_orders = resolved_mode in {
            RunMode.SIM,
            RunMode.PAPER,
            RunMode.LIVE,
            RunMode.LIVE_ONE_SHARE,
            RunMode.LIVE_MICRO,
        }
        max_shares_per_order = (
            1 if resolved_mode in {RunMode.LIVE_ONE_SHARE, RunMode.LIVE_MICRO} else None
        )
        if is_live_like and event_replay_mode != EventReplayMode.OFF:
            print(
                "[SAFETY] Replay request detected in live-like mode. "
                "Forcing EVENT_REPLAY_MODE=OFF."
            )
            event_replay_mode = EventReplayMode.OFF
        return cls(
            resolved_mode=resolved_mode,
            is_live_like=is_live_like,
            allow_orders=allow_orders,
            max_shares_per_order=max_shares_per_order,
            event_replay_mode=event_replay_mode,
        )

    def describe(self) -> str:
        return (
            "mode={mode} live_like={live_like} allow_orders={allow_orders} "
            "max_shares_per_order={max_shares} event_replay={replay}"
        ).format(
            mode=self.resolved_mode.value,
            live_like=self.is_live_like,
            allow_orders=self.allow_orders,
            max_shares=self.max_shares_per_order,
            replay=self.event_replay_mode.value,
        )
