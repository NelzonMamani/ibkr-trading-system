from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModeAuthority:
    requested_mode: str
    effective_mode: str
    execution_enabled: bool
    trade_enabled: bool
    scan_only: bool
    reason: str


def normalize_mode(mode_value: str | None) -> str:
    normalized = str(mode_value or "").strip().upper()
    if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
        return "READ_ONLY"
    if normalized in {"SIM", "SIMULATION"}:
        return "SIM"
    if normalized in {"PAPER"}:
        return "PAPER"
    if normalized in {"LIVE", "LIVE_MICRO", "LIVE_1SHARE", "LIVE-1SHARE", "LIVE_ONE_SHARE"}:
        return "LIVE"
    return "READ_ONLY"


def resolve_mode_authority(mode_value: str | None, execution_enabled: bool) -> ModeAuthority:
    requested_mode = normalize_mode(mode_value)
    env_run_mode = normalize_mode(os.getenv("RUN_MODE"))
    execution_enabled_bool = bool(execution_enabled)
    reason = ""

    if env_run_mode == "PAPER" and requested_mode != "PAPER":
        requested_mode = "PAPER"
        reason = "env_run_mode_paper_priority"

    if requested_mode in {"SIM", "READ_ONLY"}:
        authority = ModeAuthority(
            requested_mode=requested_mode,
            effective_mode=requested_mode,
            execution_enabled=execution_enabled_bool,
            trade_enabled=False,
            scan_only=True,
            reason=reason or "mode_non_executable",
        )
    elif requested_mode in {"PAPER", "LIVE"} and execution_enabled_bool:
        authority = ModeAuthority(
            requested_mode=requested_mode,
            effective_mode=requested_mode,
            execution_enabled=execution_enabled_bool,
            trade_enabled=True,
            scan_only=False,
            reason=reason or "executable_mode_enabled",
        )
    else:
        authority = ModeAuthority(
            requested_mode=requested_mode,
            effective_mode=requested_mode,
            execution_enabled=execution_enabled_bool,
            trade_enabled=False,
            scan_only=True,
            reason=reason or "execution_disabled_observational",
        )

    if authority.requested_mode == "PAPER":
        assert authority.effective_mode == "PAPER", "MODE_DOWNGRADE_NOT_ALLOWED"

    print(
        "[MODE][TRACE]",
        f"requested={authority.requested_mode}",
        f"env_RUN_MODE={os.getenv('RUN_MODE')}",
        f"env_EXECUTION_ENABLED={os.getenv('EXECUTION_ENABLED')}",
        f"effective={authority.effective_mode}",
        f"reason={authority.reason}",
    )
    return authority
