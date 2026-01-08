"""Read-only guardrail for IBKR order actions."""

from __future__ import annotations

from config.runtime_config import get_ibkr_readonly_enabled


_BLOCKED_ACTIONS = {"PLACE_ORDER", "MODIFY_ORDER", "CANCEL_ORDER"}


def assert_read_only_allows(action: str) -> None:
    """Raise if read-only mode is enabled and the action is restricted."""
    normalized = (action or "").upper()
    if get_ibkr_readonly_enabled() and normalized in _BLOCKED_ACTIONS:
        raise RuntimeError(f"Read-only enabled: blocking broker action {normalized}")


def validate_read_only_guard() -> None:
    """Run a guard self-test when read-only mode is enabled."""
    if not get_ibkr_readonly_enabled():
        return
    try:
        assert_read_only_allows("PLACE_ORDER")
    except RuntimeError:
        print("[CONFIG][VALIDATION] Read-only guard enforced")
        return
    raise RuntimeError("Read-only enabled but guard did not block PLACE_ORDER")
