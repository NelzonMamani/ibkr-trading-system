from __future__ import annotations

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
    execution_enabled_bool = bool(execution_enabled)

    if requested_mode in {"SIM", "READ_ONLY"}:
        return ModeAuthority(
            requested_mode=requested_mode,
            effective_mode=requested_mode,
            execution_enabled=execution_enabled_bool,
            trade_enabled=False,
            scan_only=True,
            reason="mode_non_executable",
        )

    if requested_mode in {"PAPER", "LIVE"} and execution_enabled_bool:
        return ModeAuthority(
            requested_mode=requested_mode,
            effective_mode=requested_mode,
            execution_enabled=execution_enabled_bool,
            trade_enabled=True,
            scan_only=False,
            reason="executable_mode_enabled",
        )

    return ModeAuthority(
        requested_mode=requested_mode,
        effective_mode=requested_mode,
        execution_enabled=execution_enabled_bool,
        trade_enabled=False,
        scan_only=True,
        reason="execution_disabled_observational",
    )
