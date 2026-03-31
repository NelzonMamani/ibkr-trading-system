"""
Define authoritative runtime settings for the trading system.

This module exposes backwards-compatible accessors backed by config_resolver.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from enum import Enum

from src.config.config_resolver import get_config
from src.config.trading_config import MAX_HOLD_TICKS, MIN_HOLD_TICKS


class RunMode(str, Enum):
    SIM = "SIM"
    READ_ONLY = "READ_ONLY"
    PAPER = "PAPER"
    LIVE = "LIVE"


DEFAULT_RUN_MODE: RunMode = RunMode.LIVE
DEFAULT_CAPITAL: float = float(os.getenv("TRADING_DEFAULT_CAPITAL", "160"))


class RuntimeConfigError(RuntimeError):
    """Raised when runtime configuration violates safety rules."""


class EventReplayMode(str, Enum):
    OFF = "OFF"
    CYCLE = "CYCLE"
    RUN = "RUN"


DEFAULT_EVENT_REPLAY_MODE: EventReplayMode = EventReplayMode.CYCLE


class ExecutionLifecycleMode(str, Enum):
    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    IBKR_STRICT = "IBKR_STRICT"


DEFAULT_EXECUTION_LIFECYCLE_MODE: ExecutionLifecycleMode = ExecutionLifecycleMode.LEGACY


def _with_default(name: str, default):
    value = get_config(name)
    return default if value is None else value


def get_run_mode() -> RunMode:
    return RunMode(get_config("RUN_MODE_EFFECTIVE"))


def get_default_capital(default: float = DEFAULT_CAPITAL) -> float:
    return float(os.getenv("TRADING_DEFAULT_CAPITAL", str(default)))


def get_config_max_position_pct(default: float = 0.1) -> float:
    return float(os.getenv("CONFIG_MAX_POSITION_PCT", str(default)))


def is_live_read_only_required() -> bool:
    return get_run_mode() == RunMode.READ_ONLY


def get_event_replay_mode(run_mode: RunMode | None = None) -> EventReplayMode:
    return EventReplayMode(get_config("EVENT_REPLAY_MODE_EFFECTIVE"))


def get_execution_lifecycle_mode(default: str = DEFAULT_EXECUTION_LIFECYCLE_MODE.value) -> ExecutionLifecycleMode:
    resolved = str(_with_default("EXECUTION_LIFECYCLE_MODE", default)).upper()
    try:
        return ExecutionLifecycleMode(resolved)
    except ValueError:
        print(
            "[CONFIG][WARN] "
            f"key=EXECUTION_LIFECYCLE_MODE invalid={resolved} fallback={DEFAULT_EXECUTION_LIFECYCLE_MODE.value}"
        )
        return DEFAULT_EXECUTION_LIFECYCLE_MODE


def _resolve_runtime_authority() -> tuple[str, bool]:
    """Return the resolved runtime mode and whether order execution is allowed."""
    from src.core.managers.runtime_mode_manager import RuntimeModeManager

    resolved = RuntimeModeManager.resolve()
    resolved_mode = str(
        getattr(getattr(resolved, "resolved_mode", None), "value", getattr(resolved, "resolved_mode", get_run_mode()))
    ).upper()
    allow_orders = bool(getattr(resolved, "allow_orders", False))
    return resolved_mode, allow_orders


def get_ibkr_readonly_enabled(default: bool = True) -> bool:
    run_mode, allow_orders = _resolve_runtime_authority()

    # Runtime authority is the single source of truth for broker mutability.
    if run_mode == RunMode.READ_ONLY.value:
        return True
    if not allow_orders:
        return True
    return False


def get_ibkr_api_write_allowed(default: bool = True) -> bool:
    run_mode, allow_orders = _resolve_runtime_authority()
    if run_mode == RunMode.READ_ONLY.value:
        return False
    return allow_orders


def get_execution_enabled(default: bool = False) -> bool:
    run_mode, allow_orders = _resolve_runtime_authority()
    if run_mode == RunMode.READ_ONLY.value:
        return False
    return allow_orders


def is_execution_enabled(run_mode: RunMode | None = None) -> bool:
    if run_mode is None:
        return get_execution_enabled()
    return execution_allowed(run_mode)


def execution_allowed(run_mode: RunMode | str | None) -> bool:
    normalized = str(getattr(run_mode, "value", run_mode) or "").upper()
    if normalized == RunMode.READ_ONLY.value:
        return False
    if normalized == RunMode.SIM.value:
        return False
    return normalized in {RunMode.LIVE.value, RunMode.PAPER.value}


def broker_orders_allowed(run_mode: RunMode | str | None) -> bool:
    normalized = str(getattr(run_mode, "value", run_mode) or "").upper()
    return normalized in {RunMode.LIVE.value, RunMode.PAPER.value}


def get_ibkr_host(default: str = "127.0.0.1") -> str:
    return str(_with_default("IBKR_HOST", default))


def resolve_ibkr_connection() -> tuple[str, int, int, str]:
    raw_run_mode = (
        os.getenv("RUN_MODE")
        or get_config("RUN_MODE_EFFECTIVE")
        or get_config("RUN_MODE")
        or RunMode.READ_ONLY.value
    )
    run_mode = str(raw_run_mode).upper()
    host = str(os.getenv("IBKR_HOST") or _with_default("IBKR_HOST", "127.0.0.1"))

    env_port = os.getenv("IBKR_PORT")
    if env_port is not None:
        port = int(env_port)
    elif run_mode == RunMode.LIVE.value:
        port = 7496
    else:
        port = 7497

    client_id = int(
        os.getenv("IBKR_CLIENT_ID") or _with_default("IBKR_CLIENT_ID", 7)
    )

    if run_mode == RunMode.LIVE.value and port != 7496:
        # Defer enforcement to runtime
        print("[CONFIG WARNING] LIVE mode using non-standard IBKR port:", port)
    if run_mode in {RunMode.PAPER.value, RunMode.SIM.value} and port != 7497:
        raise RuntimeConfigError("PAPER mode must use port 7497")

    return host, port, client_id, run_mode


def get_ibkr_port(default: int = 7497) -> int:
    _, port, _, _ = resolve_ibkr_connection()
    return port


def get_ibkr_client_id(default: int = 7) -> int:
    _, _, client_id, _ = resolve_ibkr_connection()
    return client_id


def get_ibkr_snapshot_timeout_seconds(default: int = 5) -> int:
    return int(_with_default("IBKR_SNAPSHOT_TIMEOUT_SECONDS", default))


def get_ibkr_snapshot_max_age_seconds(default: int = 15) -> int:
    return int(_with_default("IBKR_SNAPSHOT_MAX_AGE_SECONDS", default))


def get_ibkr_market_data_type(default: str = "LIVE") -> str:
    return str(_with_default("IBKR_MARKET_DATA_TYPE", default))


def get_ibkr_max_symbols_per_cycle(default: int = 50) -> int:
    return int(_with_default("IBKR_MAX_SYMBOLS_PER_CYCLE", default))


def get_ibkr_fallback_enabled(default: bool = False) -> bool:
    return bool(_with_default("IBKR_FALLBACK_ENABLED", default))


def get_ibkr_fallback_source(default: str = "STATIC") -> str:
    return str(_with_default("IBKR_FALLBACK_SOURCE", default))


def get_ibkr_auto_lockdown_enabled(default: bool = False) -> bool:
    return bool(_with_default("IBKR_AUTO_LOCKDOWN_ENABLED", default))


def get_scanner_mode(default: str = "TEACHING") -> str:
    return str(_with_default("SCANNER_MODE_EFFECTIVE", default))


def get_scanner_symbols(default: list[str] | None = None) -> list[str]:
    resolved = get_config("SCANNER_SYMBOLS")
    if not resolved:
        return default or []
    return list(resolved)


def get_watchlist_print_every_n_cycles(default: int = 20) -> int:
    return int(_with_default("WATCHLIST_PRINT_EVERY_N_CYCLES", default))


def get_intent_dedup_selftest_enabled(default: bool = False) -> bool:
    return bool(_with_default("INTENT_DEDUP_SELFTEST_ENABLED", default))


def get_ibkr_order_translation_enabled() -> bool:
    return get_execution_enabled() and bool(get_config("IBKR_ORDER_TRANSLATION_ENABLED"))


def get_ibkr_default_exchange(default: str = "SMART") -> str:
    return str(_with_default("IBKR_DEFAULT_EXCHANGE", default))


def get_ibkr_default_currency(default: str = "USD") -> str:
    return str(_with_default("IBKR_DEFAULT_CURRENCY", default))


def get_ibkr_order_submission_enabled(default: bool = False) -> bool:
    run_mode, allow_orders = _resolve_runtime_authority()

    if run_mode == RunMode.READ_ONLY.value:
        return False

    return allow_orders


def get_ibkr_kill_switch(default: bool = True) -> bool:
    return bool(_with_default("IBKR_KILL_SWITCH", default))


def get_learning_enabled(run_mode: RunMode | None = None) -> bool:
    resolved_mode = run_mode or get_run_mode()
    if resolved_mode == RunMode.LIVE:
        return bool(_with_default("LEARNING_LIVE_ENABLED", False))
    return bool(_with_default("LEARNING_ENABLED", True))


def get_ibkr_max_orders_per_run(default: int = 1) -> int:
    return int(_with_default("IBKR_MAX_ORDERS_PER_RUN", default))


def get_risk_profile_name(default: str = "NORMAL") -> str:
    return str(_with_default("RISK_PROFILE", default))


def get_risk_account_equity(default: float = 100000.0) -> float:
    return float(_with_default("RISK_ACCOUNT_EQUITY", default))


def get_daily_loss_warning_limit(default: float = 5.0) -> float:
    return float(_with_default("DAILY_LOSS_WARNING_LIMIT", default))


def get_daily_loss_hard_limit(default: float = 10.0) -> float:
    return float(_with_default("DAILY_LOSS_HARD_LIMIT", default))


def get_ibkr_submit_only_symbol(default: str | None = None) -> str | None:
    value = get_config("IBKR_SUBMIT_ONLY_SYMBOL")
    return default if value is None else str(value)


def get_ibkr_paper_only_enforced(default: bool = True) -> bool:
    run_mode = get_run_mode()
    if run_mode == RunMode.LIVE:
        return False
    return bool(_with_default("IBKR_PAPER_ONLY_ENFORCED", default))


def get_ibkr_paper_host(default: str = "127.0.0.1") -> str:
    return str(_with_default("IBKR_PAPER_HOST", default))


def get_ibkr_paper_port(default: int = 7497) -> int:
    return int(_with_default("IBKR_PAPER_PORT", default))


def get_ibkr_live_port(default: int = 7496) -> int:
    return int(_with_default("IBKR_LIVE_PORT", default))


def get_ibkr_ack_timeout_seconds(default: int = 10) -> int:
    return int(_with_default("IBKR_ACK_TIMEOUT_SECONDS", default))


def get_ibkr_client_id_order_submit(default: int = 9012) -> int:
    return int(_with_default("IBKR_CLIENT_ID_ORDER_SUBMIT", default))


def get_ibkr_guard_persist_path(default: str = "runtime/submission_guard.json") -> str:
    return str(_with_default("IBKR_GUARD_PERSIST_PATH", default))


def get_persistence_enabled(default: bool = True) -> bool:
    return bool(_with_default("PERSISTENCE_ENABLED", default))


def get_persistence_backend(default: str = "sqlite") -> str:
    return str(_with_default("PERSISTENCE_BACKEND", default))


def get_persistence_sqlite_path(default: str = "data/ibkr_system.db") -> str:
    return str(_with_default("PERSISTENCE_SQLITE_PATH", default))


def get_persistence_jsonl_mirror_enabled(default: bool = False) -> bool:
    return bool(_with_default("PERSISTENCE_JSONL_MIRROR_ENABLED", default))


def get_audit_hash_chain_enabled(default: bool = True) -> bool:
    return bool(_with_default("AUDIT_HASH_CHAIN_ENABLED", default))


def get_audit_verify_on_start(default: bool = False) -> bool:
    return bool(_with_default("AUDIT_VERIFY_ON_START", default))


def get_persist_flush_each_cycle(default: bool = True) -> bool:
    return bool(_with_default("PERSIST_FLUSH_EACH_CYCLE", default))


@dataclass
class RuntimeConfig:
    """
    Minimal runtime configuration context for deterministic engine evaluation.

    This container intentionally mirrors the authoritative trading thresholds to
    make pure decision functions testable without importing global constants in
    multiple places.
    """

    min_hold_ticks: int = MIN_HOLD_TICKS
    max_hold_ticks: int = MAX_HOLD_TICKS
