"""Execution guardrail for IBKR order actions."""

from __future__ import annotations

from src.config.runtime_config import (
    get_execution_enabled,
    get_ibkr_readonly_enabled,
    get_run_mode,
    is_execution_enabled,
)


_BLOCKED_ACTIONS = {"PLACE_ORDER", "MODIFY_ORDER", "CANCEL_ORDER"}


def assert_read_only_allows(action: str) -> None:
    """Raise if execution is disabled and the action is restricted."""
    normalized = (action or "").upper()
    if normalized not in _BLOCKED_ACTIONS:
        return
    run_mode = get_run_mode().value
    execution_flag = get_execution_enabled()
    readonly_enabled = get_ibkr_readonly_enabled()
    if readonly_enabled:
        raise RuntimeError(
            "IBKR read-only enabled: blocking broker action "
            f"{normalized} (run_mode={run_mode} execution_enabled={execution_flag})"
        )
    if not is_execution_enabled():
        raise RuntimeError(
            "Execution disabled: blocking broker action "
            f"{normalized} (run_mode={run_mode} execution_enabled={execution_flag})"
        )


def validate_read_only_guard() -> None:
    """Run a guard self-test when execution is disabled."""
    readonly_enabled = get_ibkr_readonly_enabled()
    if is_execution_enabled() and not readonly_enabled:
        print("[CONFIG][VALIDATION] Execution enabled; guard allows broker actions")
        return
    print("[CONFIG][VALIDATION] Running execution guard self-test")
    try:
        assert_read_only_allows("PLACE_ORDER")
    except RuntimeError:
        print("[CONFIG][VALIDATION] Execution guard enforced")
        return
    raise RuntimeError(
        "Execution guard did not block PLACE_ORDER when read-only or execution disabled"
    )
