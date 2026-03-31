from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import get_config
from src.config.runtime_config import EventReplayMode, RunMode
from src.core.mode_authority import resolve_mode_authority


@dataclass(frozen=True)
class RuntimeModeManager:
    resolved_mode: RunMode
    is_live_like: bool
    allow_orders: bool
    max_shares_per_order: int | None
    event_replay_mode: EventReplayMode

    @classmethod
    def resolve(cls) -> "RuntimeModeManager":
        run_mode_raw = get_config("RUN_MODE")
        execution_enabled_raw = get_config("EXECUTION_ENABLED")
        run_mode_normalized = str(get_config("RUN_MODE_EFFECTIVE")).upper()
        execution_enabled_normalized = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
        print(
            "[MODE][INPUT] "
            f"run_mode_raw={run_mode_raw} execution_enabled_raw={execution_enabled_raw}"
        )
        print(
            "[MODE][NORMALIZED] "
            f"run_mode={run_mode_normalized} execution_enabled={execution_enabled_normalized}"
        )
        authority = resolve_mode_authority(
            run_mode_normalized,
            execution_enabled_normalized,
        )
        print(
            "[MODE][AUTHORITY] "
            f"effective_mode={authority.effective_mode} "
            f"trade_enabled={authority.trade_enabled} "
            f"scan_only={authority.scan_only} reason={authority.reason}"
        )
        resolved_mode = RunMode(authority.effective_mode)
        event_replay_mode = EventReplayMode(get_config("EVENT_REPLAY_MODE_EFFECTIVE"))
        risk_profile = str(get_config("RISK_PROFILE") or "NORMAL").strip().upper()
        execution_enabled_effective = authority.trade_enabled
        is_live_like = resolved_mode in {RunMode.LIVE, RunMode.READ_ONLY}
        allow_orders = execution_enabled_effective
        max_shares_per_order = 1 if risk_profile == "MICRO" else None
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
