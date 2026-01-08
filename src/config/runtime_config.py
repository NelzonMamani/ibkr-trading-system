"""
Define authoritative runtime settings for the trading system.

This module is the single source of truth for runtime modes and replay modes.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from enum import Enum

from config.trading_config import MAX_HOLD_TICKS, MIN_HOLD_TICKS


class RunMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"
    LIVE_READ_ONLY = "LIVE_READ_ONLY"
    LIVE_MICRO = "LIVE_MICRO"


DEFAULT_RUN_MODE: RunMode = RunMode.SIM


def get_run_mode() -> RunMode:
    """
    Authoritative runtime mode resolver.

    Resolution order:
    1) ENV: RUN_MODE
    2) DEFAULT_RUN_MODE (SIM)
    """
    raw = (os.getenv("RUN_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_RUN_MODE

    try:
        return RunMode(raw)
    except ValueError:
        print(f"[RUNTIME] Invalid RUN_MODE='{raw}'. Falling back to SAFE default SIM.")
        return RunMode.SIM


def get_ibkr_readonly_enabled(default: bool = True) -> bool:
    raw = (os.getenv("IBKR_READONLY_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_ibkr_host(default: str = "127.0.0.1") -> str:
    return (os.getenv("IBKR_HOST") or default).strip() or default


def get_ibkr_port(default: int = 7497) -> int:
    raw = (os.getenv("IBKR_PORT") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(f"[RUNTIME] Invalid IBKR_PORT='{raw}'. Falling back to default {default}.")
        return default


def get_ibkr_client_id(default: int = 7) -> int:
    raw = (os.getenv("IBKR_CLIENT_ID") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_CLIENT_ID='{raw}'. Falling back to default {default}."
        )
        return default


def get_ibkr_snapshot_timeout_seconds(default: int = 5) -> int:
    raw = (os.getenv("IBKR_SNAPSHOT_TIMEOUT_SECONDS") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            "[RUNTIME] Invalid IBKR_SNAPSHOT_TIMEOUT_SECONDS='" + raw + "'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_snapshot_max_age_seconds(default: int = 15) -> int:
    raw = (os.getenv("IBKR_SNAPSHOT_MAX_AGE_SECONDS") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            "[RUNTIME] Invalid IBKR_SNAPSHOT_MAX_AGE_SECONDS='" + raw + "'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_market_data_type(default: str = "LIVE") -> str:
    raw = (os.getenv("IBKR_MARKET_DATA_TYPE") or default).strip().upper()
    if raw in {"LIVE", "DELAYED", "DELAYED_FROZEN", "FROZEN"}:
        return raw
    if raw:
        print(f"[RUNTIME] Invalid IBKR_MARKET_DATA_TYPE='{raw}'. Falling back to default {default}.")
    return default


def get_ibkr_max_symbols_per_cycle(default: int = 50) -> int:
    raw = (os.getenv("IBKR_MAX_SYMBOLS_PER_CYCLE") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_MAX_SYMBOLS_PER_CYCLE='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_fallback_enabled(default: bool = False) -> bool:
    raw = (os.getenv("IBKR_FALLBACK_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_ibkr_fallback_source(default: str = "STATIC") -> str:
    raw = (os.getenv("IBKR_FALLBACK_SOURCE") or default).strip().upper()
    return raw or default


def get_ibkr_auto_lockdown_enabled(default: bool = False) -> bool:
    raw = (os.getenv("IBKR_AUTO_LOCKDOWN_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_scanner_mode(default: str = "TEACHING") -> str:
    raw = (os.getenv("SCANNER_MODE") or default).strip().upper()
    if raw in {"TEACHING", "LIVE_READONLY"}:
        return raw
    print(f"[RUNTIME] Invalid SCANNER_MODE='{raw}'. Falling back to default {default}.")
    return default


def get_scanner_symbols(default: list[str] | None = None) -> list[str]:
    raw = (os.getenv("SCANNER_SYMBOLS") or os.getenv("IBKR_SCAN_SYMBOLS") or "").strip()
    if not raw:
        return default or []
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def get_ibkr_order_translation_enabled() -> bool:
    return (os.getenv("IBKR_ORDER_TRANSLATION_ENABLED") or "").strip().lower() == "true"


def get_ibkr_default_exchange(default: str = "SMART") -> str:
    return (os.getenv("IBKR_DEFAULT_EXCHANGE") or default).strip() or default


def get_ibkr_default_currency(default: str = "USD") -> str:
    return (os.getenv("IBKR_DEFAULT_CURRENCY") or default).strip() or default


def get_ibkr_order_submission_enabled(default: bool = False) -> bool:
    raw = (os.getenv("IBKR_ORDER_SUBMISSION_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_ibkr_kill_switch(default: bool = True) -> bool:
    raw = (os.getenv("IBKR_KILL_SWITCH") or "").strip().lower()
    if raw in {"false", "0", "no"}:
        return False
    if raw in {"true", "1", "yes"}:
        return True
    return default


def get_ibkr_max_orders_per_run(default: int = 1) -> int:
    raw = (os.getenv("IBKR_MAX_ORDERS_PER_RUN") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_MAX_ORDERS_PER_RUN='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_live_micro_max_concurrent_trades(default: int = 1) -> int:
    raw = (os.getenv("LIVE_MICRO_MAX_CONCURRENT_TRADES") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid LIVE_MICRO_MAX_CONCURRENT_TRADES='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_live_micro_max_trades_per_day(default: int = 3) -> int:
    raw = (os.getenv("LIVE_MICRO_MAX_TRADES_PER_DAY") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid LIVE_MICRO_MAX_TRADES_PER_DAY='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_live_micro_daily_max_loss(default: float = 5.0) -> float:
    raw = (os.getenv("LIVE_MICRO_DAILY_MAX_LOSS") or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid LIVE_MICRO_DAILY_MAX_LOSS='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_live_micro_max_consecutive_losses(default: int = 1) -> int:
    raw = (os.getenv("LIVE_MICRO_MAX_CONSECUTIVE_LOSSES") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid LIVE_MICRO_MAX_CONSECUTIVE_LOSSES='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_submit_only_symbol(default: str | None = None) -> str | None:
    raw = (os.getenv("IBKR_SUBMIT_ONLY_SYMBOL") or "").strip().upper()
    return raw or default


def get_ibkr_paper_only_enforced(default: bool = True) -> bool:
    raw = (os.getenv("IBKR_PAPER_ONLY_ENFORCED") or "").strip().lower()
    if raw in {"false", "0", "no"}:
        return False
    if raw in {"true", "1", "yes"}:
        return True
    return default


def get_ibkr_paper_host(default: str = "127.0.0.1") -> str:
    return (os.getenv("IBKR_PAPER_HOST") or default).strip() or default


def get_ibkr_paper_port(default: int = 7497) -> int:
    raw = (os.getenv("IBKR_PAPER_PORT") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_PAPER_PORT='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_live_port(default: int = 7496) -> int:
    raw = (os.getenv("IBKR_LIVE_PORT") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_LIVE_PORT='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_ack_timeout_seconds(default: int = 10) -> int:
    raw = (os.getenv("IBKR_ACK_TIMEOUT_SECONDS") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_ACK_TIMEOUT_SECONDS='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_client_id_order_submit(default: int = 9012) -> int:
    raw = (os.getenv("IBKR_CLIENT_ID_ORDER_SUBMIT") or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(
            f"[RUNTIME] Invalid IBKR_CLIENT_ID_ORDER_SUBMIT='{raw}'. "
            f"Falling back to default {default}."
        )
        return default


def get_ibkr_guard_persist_path(default: str = "runtime/submission_guard.json") -> str:
    return (os.getenv("IBKR_GUARD_PERSIST_PATH") or default).strip() or default


def get_persistence_enabled(default: bool = True) -> bool:
    raw = (os.getenv("PERSISTENCE_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_persistence_backend(default: str = "sqlite") -> str:
    raw = (os.getenv("PERSISTENCE_BACKEND") or default).strip().lower()
    return raw or default


def get_persistence_sqlite_path(default: str = "data/ibkr_system.db") -> str:
    return (os.getenv("PERSISTENCE_SQLITE_PATH") or default).strip() or default


def get_persistence_jsonl_mirror_enabled(default: bool = False) -> bool:
    raw = (os.getenv("PERSISTENCE_JSONL_MIRROR_ENABLED") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_audit_hash_chain_enabled(default: bool = True) -> bool:
    raw = (os.getenv("AUDIT_HASH_CHAIN_ENABLED") or "").strip().lower()
    if raw in {"false", "0", "no"}:
        return False
    if raw in {"true", "1", "yes"}:
        return True
    return default


def get_audit_verify_on_start(default: bool = False) -> bool:
    raw = (os.getenv("AUDIT_VERIFY_ON_START") or "").strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return default


def get_persist_flush_each_cycle(default: bool = True) -> bool:
    raw = (os.getenv("PERSIST_FLUSH_EACH_CYCLE") or "").strip().lower()
    if raw in {"false", "0", "no"}:
        return False
    if raw in {"true", "1", "yes"}:
        return True
    return default


class EventReplayMode(str, Enum):
    OFF = "OFF"
    CYCLE = "CYCLE"
    RUN = "RUN"


DEFAULT_EVENT_REPLAY_MODE: EventReplayMode = EventReplayMode.CYCLE


def get_event_replay_mode(run_mode: RunMode) -> EventReplayMode:
    """
    Resolve EVENT_REPLAY_MODE using runtime-safe rules.

    Resolution order:
    1) LIVE/LIVE_READ_ONLY/LIVE_MICRO always forces OFF
    2) ENV: EVENT_REPLAY_MODE
    3) DEFAULT_EVENT_REPLAY_MODE (CYCLE)
    """

    if run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
        return EventReplayMode.OFF

    raw = (os.getenv("EVENT_REPLAY_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_EVENT_REPLAY_MODE

    try:
        return EventReplayMode(raw)
    except ValueError:
        print(
            f"[RUNTIME] Invalid EVENT_REPLAY_MODE='{raw}'. "
            f"Falling back to default {DEFAULT_EVENT_REPLAY_MODE}."
        )
        return DEFAULT_EVENT_REPLAY_MODE


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
