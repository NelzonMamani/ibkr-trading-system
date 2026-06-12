"""Shared Ross runtime safety decisions for PR1 guardrails."""

from __future__ import annotations

from typing import Any


VALIDATION_MODES = {"SIM", "PAPER"}
LIVE_MODES = {"LIVE", "READ_ONLY"}


def normalize_run_mode(mode: Any) -> str:
    value = getattr(mode, "value", mode)
    return str(value or "").strip().upper()


def is_live_mode(mode: Any) -> bool:
    return normalize_run_mode(mode) == "LIVE"


def is_read_only_mode(mode: Any) -> bool:
    return normalize_run_mode(mode) == "READ_ONLY"


def is_live_like_mode(mode: Any) -> bool:
    return normalize_run_mode(mode) in LIVE_MODES


def is_validation_mode(mode: Any) -> bool:
    return normalize_run_mode(mode) in VALIDATION_MODES


def validation_override_allowed(mode: Any, requested: bool) -> bool:
    return bool(requested) and is_validation_mode(mode)


def synthetic_intent_allowed(mode: Any, requested: bool) -> bool:
    return validation_override_allowed(mode, requested)


def validation_block_reason(mode: Any) -> str:
    normalized = normalize_run_mode(mode)
    if normalized == "LIVE":
        return "not_live_safe"
    if normalized == "READ_ONLY":
        return "read_only_not_tradability"
    return "explicit_validation_flag_required"


def log_validation_override_active(mode: Any, reason: str) -> None:
    print(
        "[ROSS][VALIDATION_OVERRIDE][ACTIVE] "
        f"mode={normalize_run_mode(mode)} reason={reason}"
    )


def log_validation_override_blocked(mode: Any, reason: str | None = None) -> None:
    print(
        "[ROSS][VALIDATION_OVERRIDE][BLOCKED] "
        f"mode={normalize_run_mode(mode)} reason={reason or validation_block_reason(mode)}"
    )


def log_no_setup_no_trade(symbol: Any, reason: str) -> None:
    print(
        "[ROSS][NO_SETUP][NO_TRADE] "
        f"symbol={str(symbol or 'UNKNOWN').upper()} reason={reason}"
    )


def log_fallback_intent_blocked(mode: Any, reason: str = "real_setup_required") -> None:
    print(
        "[ROSS][FALLBACK_INTENT][BLOCKED] "
        f"mode={normalize_run_mode(mode)} reason={reason}"
    )
