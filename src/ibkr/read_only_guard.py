"""Execution guardrail for IBKR order actions."""

from __future__ import annotations

from src.config.runtime_config import (
    RunMode,
    get_execution_enabled,
    get_ibkr_api_write_allowed,
    get_ibkr_readonly_enabled,
    get_run_mode,
    is_execution_enabled,
)


_BLOCKED_ACTIONS = {"PLACE_ORDER", "MODIFY_ORDER", "CANCEL_ORDER"}


def assert_read_only_allows(
    action: str,
    run_mode_override: RunMode | None = None,
    execution_enabled_override: bool | None = None,
) -> None:
    """Raise if execution is disabled and the action is restricted."""
    normalized = (action or "").upper()
    if normalized not in _BLOCKED_ACTIONS:
        return

    resolved_run_mode = run_mode_override or get_run_mode()
    run_mode = str(getattr(resolved_run_mode, "value", resolved_run_mode)).upper()
    execution_flag = (
        execution_enabled_override
        if execution_enabled_override is not None
        else get_execution_enabled()
    )
    if run_mode == RunMode.PAPER.value:
        readonly_enabled = False
    elif run_mode in {RunMode.READ_ONLY.value, RunMode.SIM.value}:
        readonly_enabled = True
    else:
        readonly_enabled = get_ibkr_readonly_enabled()
    api_write_allowed = get_ibkr_api_write_allowed()

    if readonly_enabled or not api_write_allowed:
        raise RuntimeError(
            "IBKR read-only authority enabled: blocking broker action "
            f"{normalized} (run_mode={run_mode} execution_enabled={execution_flag} "
            f"readonly_enabled={readonly_enabled} api_write_allowed={api_write_allowed})"
        )

    if not execution_flag:
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
