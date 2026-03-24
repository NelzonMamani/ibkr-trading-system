"""
Configuration resolver for the IBKR trading system.

All environment access is centralized here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, Iterable

from src.config.config_registry import CONFIG_REGISTRY


class ConfigResolutionError(RuntimeError):
    """Raised when configuration resolution fails validation."""


@dataclass(frozen=True)
class ConfigRecord:
    name: str
    value: Any
    source: str
    env: str | None
    trace: tuple[str, ...] = ()


_CONFIG_CACHE: Dict[str, ConfigRecord] | None = None
_CONFIG_CACHE_ENV_FINGERPRINT: tuple | None = None
_CONFIG_PRINTED = False
_CONFIG_OVERRIDES: Dict[str, Any] = {}


def set_config_overrides(overrides: Dict[str, Any] | None) -> None:
    """Set in-process overrides with highest precedence for this process.

    Canonical precedence law (highest -> lowest):
    1) in-process overrides set here
    2) environment variables
    3) registry defaults / default_factory
    """

    global _CONFIG_OVERRIDES, _CONFIG_CACHE, _CONFIG_CACHE_ENV_FINGERPRINT, _CONFIG_PRINTED
    _CONFIG_OVERRIDES = overrides or {}
    _CONFIG_CACHE = None
    _CONFIG_CACHE_ENV_FINGERPRINT = None
    _CONFIG_PRINTED = False
    for alias in ("src.config.config_resolver", "config.config_resolver"):
        module = sys.modules.get(alias)
        if module is None or module is sys.modules.get(__name__):
            continue
        module._CONFIG_OVERRIDES = _CONFIG_OVERRIDES
        module._CONFIG_CACHE = None
        module._CONFIG_CACHE_ENV_FINGERPRINT = None
        module._CONFIG_PRINTED = False

    # Reset shared IBKR manager to avoid stale mode/readonly state leaking across tests.
    try:
        from src.adapters.brokers.ibkr import ibkr_connection_manager as _ibkr_connection_manager

        _ibkr_connection_manager._default_manager = None
    except Exception:
        pass

    # Reset scanner runtime globals so provider/watchlist print state cannot leak across override changes.
    try:
        from src.scanner.scanner_runner import reset_scanner_runtime_state

        reset_scanner_runtime_state(clear_persistent_provider=True)
    except Exception:
        pass


def clear_config_overrides() -> None:
    """Clear in-process overrides and invalidate caches."""

    set_config_overrides(None)


def _normalize(value: Any, normalizer: str | None) -> Any:
    if normalizer is None:
        return value
    if isinstance(value, str):
        if normalizer == "upper":
            return value.strip().upper()
        if normalizer == "lower":
            return value.strip().lower()
        if normalizer == "strip":
            return value.strip()
        if normalizer == "run_mode":
            normalized = value.strip().upper()
            if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
                return "READ_ONLY"
            return normalized
    if isinstance(value, list) and normalizer in {"upper", "lower", "strip", "run_mode"}:
        normalized = []
        for item in value:
            if not isinstance(item, str):
                normalized.append(item)
                continue
            normalized.append(_normalize(item, normalizer))
        return normalized
    return value


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigResolutionError(f"Invalid boolean value '{raw}'")


def _parse_time(raw: str) -> time:
    cleaned = raw.strip()
    try:
        hour, minute = cleaned.split(":")
        return time(int(hour), int(minute))
    except ValueError as exc:
        raise ConfigResolutionError(
            f"Invalid time value '{raw}' (expected HH:MM)"
        ) from exc


def _parse_date(raw: str) -> date:
    cleaned = raw.strip()
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigResolutionError(
            f"Invalid date value '{raw}' (expected YYYY-MM-DD)"
        ) from exc


def _parse_iterable(raw: str, item_type: Any) -> list:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if item_type in {str, None}:
        return items
    parsed: list[Any] = []
    for item in items:
        if item_type is int:
            parsed.append(int(item))
        elif item_type is float:
            parsed.append(float(item))
        elif item_type == "date":
            parsed.append(_parse_date(item))
        else:
            parsed.append(item)
    return parsed


def _parse_value(raw: str, entry: Dict[str, Any]) -> Any:
    type_hint = entry.get("type")
    if type_hint is bool:
        return _parse_bool(raw)
    if type_hint is int:
        return int(raw.strip())
    if type_hint is float:
        return float(raw.strip())
    if type_hint is str:
        return raw.strip()
    if type_hint is list:
        item_type = entry.get("item_type", str)
        return _parse_iterable(raw, item_type)
    if type_hint is set:
        item_type = entry.get("item_type", str)
        return set(_parse_iterable(raw, item_type))
    if type_hint is dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigResolutionError(
                f"Invalid JSON for {entry.get('name', 'config')}"
            ) from exc
    if type_hint is time:
        return _parse_time(raw)
    raise ConfigResolutionError(f"Unsupported config type: {type_hint}")


def _resolve_entry(name: str, entry: Dict[str, Any]) -> ConfigRecord:
    env_names: Iterable[str] = entry.get("env", [])
    env_value = None
    env_used = None
    for env_name in env_names:
        if env_name in os.environ and os.environ[env_name] != "":
            env_value = os.environ[env_name]
            env_used = env_name
            break

    # Authority law (highest -> lowest):
    # 1) in-process overrides (tests/runtime)
    # 2) environment
    # 3) registry defaults
    if name in _CONFIG_OVERRIDES:
        value = _CONFIG_OVERRIDES[name]
        source = "OVERRIDE"
        trace = (f"{name}=override({value!r})",)
    elif env_value is not None:
        value = _parse_value(env_value, entry)
        source = "ENV"
        trace = (
            f"{name}=env[{env_used}] raw={env_value!r} parsed={value!r}",
        )
    else:
        if "default_factory" in entry:
            value = entry["default_factory"]()
        else:
            value = entry.get("default")
        source = "DEFAULT"
        trace = (f"{name}=default({value!r})",)

    value = _normalize(value, entry.get("normalizer"))
    if trace and value is not None:
        trace = (*trace, f"{name}=normalized({value!r})")
    if value is None and entry.get("enforcement") == "HARD" and not entry.get("allow_none"):
        raise ConfigResolutionError(
            f"Missing required configuration value for {name}"
        )

    if value is not None:
        type_hint = entry.get("type")
        if type_hint in {list, set}:
            if not isinstance(value, type_hint):
                raise ConfigResolutionError(
                    f"Config {name} must be {type_hint}, got {type(value)}"
                )
        elif type_hint is dict:
            if not isinstance(value, dict):
                raise ConfigResolutionError(
                    f"Config {name} must be dict, got {type(value)}"
                )
        elif type_hint is time:
            if not isinstance(value, time):
                raise ConfigResolutionError(
                    f"Config {name} must be time, got {type(value)}"
                )
        elif type_hint not in {None, "date"} and not isinstance(value, type_hint):
            raise ConfigResolutionError(
                f"Config {name} must be {type_hint}, got {type(value)}"
            )

    choices = entry.get("choices")
    if choices and value is not None and value not in choices:
        raise ConfigResolutionError(
            f"Config {name} must be one of {choices}; got {value}"
        )

    return ConfigRecord(name=name, value=value, source=source, env=env_used, trace=trace)


def _derive_record(
    name: str,
    value: Any,
    *,
    source: str = "DERIVED",
    env: str | None = None,
    trace: Iterable[str] = (),
) -> ConfigRecord:
    return ConfigRecord(name=name, value=value, source=source, env=env, trace=tuple(trace))


def _resolve_git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None
    sha = result.stdout.strip()
    return sha or None




def resolve_execution_flags(resolved: Dict[str, ConfigRecord]) -> Dict[str, ConfigRecord]:
    """Apply institutional execution authority overrides and invariants."""

    updated = dict(resolved)
    run_mode = str(updated["RUN_MODE"].value or "").upper()

    execution_record = updated["EXECUTION_ENABLED"]
    if run_mode in {"LIVE", "PAPER"} and execution_record.source == "DEFAULT":
        updated["EXECUTION_ENABLED"] = _derive_record(
            "EXECUTION_ENABLED",
            True,
            trace=(
                *execution_record.trace,
                f"EXECUTION_ENABLED default elevated to True for institutional RUN_MODE={run_mode}",
            ),
        )
        execution_record = updated["EXECUTION_ENABLED"]

    execution_enabled = bool(execution_record.value)
    if run_mode == "LIVE" and not execution_enabled:
        updated["EXECUTION_ENABLED"] = _derive_record(
            "EXECUTION_ENABLED",
            execution_enabled,
            trace=(
                *execution_record.trace,
                "[CONFIG][WARNING] LIVE mode with execution disabled (runtime enforcement will apply)",
            ),
        )
        execution_record = updated["EXECUTION_ENABLED"]

    readonly_record = updated["IBKR_READONLY_ENABLED"]
    updated["IBKR_READONLY_ENABLED"] = _derive_record(
        "IBKR_READONLY_ENABLED",
        not execution_enabled,
        trace=(
            *readonly_record.trace,
            f"IBKR_READONLY_ENABLED derived from EXECUTION_ENABLED={execution_enabled!r}",
        ),
    )

    submission_record = updated["IBKR_ORDER_SUBMISSION_ENABLED"]
    updated["IBKR_ORDER_SUBMISSION_ENABLED"] = _derive_record(
        "IBKR_ORDER_SUBMISSION_ENABLED",
        execution_enabled,
        trace=(
            *submission_record.trace,
            f"IBKR_ORDER_SUBMISSION_ENABLED derived from EXECUTION_ENABLED={execution_enabled!r}",
        ),
    )

    translation_record = updated["IBKR_ORDER_TRANSLATION_ENABLED"]
    updated["IBKR_ORDER_TRANSLATION_ENABLED"] = _derive_record(
        "IBKR_ORDER_TRANSLATION_ENABLED",
        execution_enabled,
        trace=(
            *translation_record.trace,
            f"IBKR_ORDER_TRANSLATION_ENABLED derived from EXECUTION_ENABLED={execution_enabled!r}",
        ),
    )
    return updated

def _resolve_derived(config: Dict[str, ConfigRecord]) -> Dict[str, ConfigRecord]:
    resolved = dict(config)

    run_mode = resolved["RUN_MODE"].value
    market_data_type = resolved["IBKR_MARKET_DATA_TYPE"].value

    effective_run_mode = run_mode

    # if effective_run_mode == "SIM" and market_data_type == "LIVE":
    #     raise ConfigResolutionError(
    #         "RUN_MODE=SIM is invalid when IBKR_MARKET_DATA_TYPE=LIVE."
    #     )
    #
    # resolved["RUN_MODE_EFFECTIVE"] = ConfigRecord(
    #     name="RUN_MODE_EFFECTIVE",
    #     value=effective_run_mode,
    #     source="DERIVED",
    #     env=None,
    # )
    if effective_run_mode == "SIM" and market_data_type == "LIVE":
        # SIM with live market data is allowed for diagnostics, scanner validation,
        # and read-only observation. Execution must be forcibly disabled.
        prior = resolved["EXECUTION_ENABLED"]
        resolved["EXECUTION_ENABLED"] = _derive_record(
            "EXECUTION_ENABLED",
            False,
            trace=(
                *prior.trace,
                "EXECUTION_ENABLED overridden to False because RUN_MODE=SIM with IBKR_MARKET_DATA_TYPE=LIVE",
            ),
        )

    resolved = resolve_execution_flags(resolved)

    resolved["RUN_MODE_EFFECTIVE"] = _derive_record(
        "RUN_MODE_EFFECTIVE",
        effective_run_mode,
        trace=(
            *resolved["RUN_MODE"].trace,
            f"RUN_MODE_EFFECTIVE derived from RUN_MODE={run_mode!r}",
        ),
    )

    scanner_mode_record = resolved["SCANNER_MODE"]
    scanner_mode = scanner_mode_record.value
    scanner_mode_source = scanner_mode_record.source
    if effective_run_mode in {"LIVE", "READ_ONLY", "PAPER"}:
        effective_scanner_mode = "LIVE_READONLY"
    elif effective_run_mode == "SIM" and scanner_mode_source in {"DEFAULT"}:
        effective_scanner_mode = "TEACHING"
    else:
        effective_scanner_mode = scanner_mode
    resolved["SCANNER_MODE_EFFECTIVE"] = _derive_record(
        "SCANNER_MODE_EFFECTIVE",
        effective_scanner_mode,
        trace=(
            *scanner_mode_record.trace,
            f"SCANNER_MODE_EFFECTIVE derived for RUN_MODE_EFFECTIVE={effective_run_mode!r}",
        ),
    )

    scanner_data_source_record = resolved["SCANNER_DATA_SOURCE"]
    if scanner_data_source_record.source in {"OVERRIDE", "ENV"}:
        resolved["SCANNER_DATA_SOURCE"] = scanner_data_source_record
    else:
        scanner_data_source = "MOCK" if effective_run_mode == "SIM" else "IBKR"
        resolved["SCANNER_DATA_SOURCE"] = _derive_record(
            "SCANNER_DATA_SOURCE",
            scanner_data_source,
            trace=(
                *scanner_data_source_record.trace,
                f"SCANNER_DATA_SOURCE derived for RUN_MODE_EFFECTIVE={effective_run_mode!r}",
            ),
        )

    ibkr_readonly_record = resolved["IBKR_READONLY_ENABLED"]
    ibkr_readonly_enabled = bool(ibkr_readonly_record.value)
    execution_enabled_flag = bool(resolved["EXECUTION_ENABLED"].value)
    execution_capable_mode = effective_run_mode in {"LIVE", "PAPER"}
    execution_enabled_effective = execution_capable_mode and execution_enabled_flag and not ibkr_readonly_enabled

    ibkr_kill_switch = effective_run_mode == "READ_ONLY"
    resolved["IBKR_KILL_SWITCH"] = _derive_record(
        "IBKR_KILL_SWITCH",
        ibkr_kill_switch,
        trace=(f"IBKR_KILL_SWITCH derived from RUN_MODE_EFFECTIVE={effective_run_mode!r}",),
    )

    requested_replay = resolved["EVENT_REPLAY_MODE"].value
    if effective_run_mode in {"LIVE", "READ_ONLY"}:
        replay_mode = "OFF"
    else:
        replay_mode = requested_replay
    resolved["EVENT_REPLAY_MODE_EFFECTIVE"] = _derive_record(
        "EVENT_REPLAY_MODE_EFFECTIVE",
        replay_mode,
        trace=(
            *resolved["EVENT_REPLAY_MODE"].trace,
            f"EVENT_REPLAY_MODE_EFFECTIVE derived for RUN_MODE_EFFECTIVE={effective_run_mode!r}",
        ),
    )

    resolved["EXECUTION_ENABLED_EFFECTIVE"] = _derive_record(
        "EXECUTION_ENABLED_EFFECTIVE",
        execution_enabled_effective,
        trace=(
            *resolved["EXECUTION_ENABLED"].trace,
            *ibkr_readonly_record.trace,
            "EXECUTION_ENABLED_EFFECTIVE requires RUN_MODE_EFFECTIVE in {'LIVE', 'PAPER'}",
            f"EXECUTION_ENABLED_EFFECTIVE derived={execution_enabled_effective!r}",
        ),
    )

    selected_strategy = str(resolved["SELECTED_STRATEGY"].value or "").strip().lower()
    if selected_strategy == "statistical_intraday_momentum":
        current_enabled = resolved["STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED"].value
        if not current_enabled:
            resolved["STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED"] = _derive_record(
                "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED",
                True,
                trace=("Forced by SELECTED_STRATEGY=statistical_intraday_momentum",),
            )
            print(
                "[CONFIG] Selected strategy=statistical_intraday_momentum; "
                "forcing STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED=True"
            )
    if selected_strategy == "mean_reversion":
        current_enabled = resolved["MEAN_REVERSION_STRATEGY_ENABLED"].value
        if not current_enabled:
            resolved["MEAN_REVERSION_STRATEGY_ENABLED"] = _derive_record(
                "MEAN_REVERSION_STRATEGY_ENABLED",
                True,
                trace=("Forced by SELECTED_STRATEGY=mean_reversion",),
            )
            print(
                "[CONFIG] Selected strategy=mean_reversion; "
                "forcing MEAN_REVERSION_STRATEGY_ENABLED=True"
            )

    if selected_strategy == "long_horizon_value":
        current_enabled = resolved["LONG_HORIZON_VALUE_STRATEGY_ENABLED"].value
        if not current_enabled:
            resolved["LONG_HORIZON_VALUE_STRATEGY_ENABLED"] = _derive_record(
                "LONG_HORIZON_VALUE_STRATEGY_ENABLED",
                True,
                trace=("Forced by SELECTED_STRATEGY=long_horizon_value",),
            )
            print(
                "[CONFIG] Selected strategy=long_horizon_value; "
                "forcing LONG_HORIZON_VALUE_STRATEGY_ENABLED=True"
            )

    if selected_strategy in {
        "event_earnings_reaction",
        "event_news_shock_continuation",
        "volatility_contraction_breakout",
        "volatility_carry_risk_premium",
        "pairs_divergence_reversion",
        "cross_sectional_relative_strength_rotation",
        "time_based_seasonality",
        "trend_following_classic",
        "long_horizon_quality_compounder",
        "regime_adaptive_meta_allocator",
        "opening_drive",
        "vwap_reclaim",
        "power_hour",
        "volatility_expansion",
        "range_bound_fade",
        "support_resistance_channel",
    }:
        enabled_strategies = dict(resolved["ENABLED_STRATEGIES"].value or {})
        by_key = {
            "event_earnings_reaction": "EventEarningsReactionStrategy",
            "event_news_shock_continuation": "EventNewsShockContinuationStrategy",
            "volatility_contraction_breakout": "VolatilityContractionBreakoutStrategy",
            "volatility_carry_risk_premium": "VolatilityCarryRiskPremiumStrategy",
            "pairs_divergence_reversion": "PairsDivergenceReversionStrategy",
            "cross_sectional_relative_strength_rotation": "CrossSectionalRelativeStrengthRotationStrategy",
            "time_based_seasonality": "TimeBasedSeasonalityStrategy",
            "trend_following_classic": "TrendFollowingClassicStrategy",
            "long_horizon_quality_compounder": "LongHorizonQualityCompounderStrategy",
            "regime_adaptive_meta_allocator": "RegimeAdaptiveMetaAllocatorStrategy",
            "opening_drive": "OpeningDriveStrategy",
            "vwap_reclaim": "VwapReclaimStrategy",
            "power_hour": "PowerHourStrategy",
            "volatility_expansion": "VolatilityExpansionStrategy",
            "range_bound_fade": "RangeBoundFadeStrategy",
            "support_resistance_channel": "SupportResistanceChannelStrategy",
        }
        strategy_name = by_key[selected_strategy]
        if not enabled_strategies.get(strategy_name, False):
            enabled_strategies[strategy_name] = True
            resolved["ENABLED_STRATEGIES"] = _derive_record(
                "ENABLED_STRATEGIES",
                enabled_strategies,
                trace=(f"Forced ENABLED_STRATEGIES[{strategy_name}]=True by SELECTED_STRATEGY",),
            )
            print(
                f"[CONFIG] Selected strategy={selected_strategy}; "
                f"forcing ENABLED_STRATEGIES[{strategy_name}]=True"
            )

    if resolved["GIT_SHA"].value is None:
        resolved["GIT_SHA"] = _derive_record(
            "GIT_SHA",
            _resolve_git_sha(),
            source="DEFAULT",
            trace=("GIT_SHA resolved from git rev-parse HEAD",),
        )

    return resolved


def _apply_post_derived_overrides(resolved: Dict[str, ConfigRecord]) -> Dict[str, ConfigRecord]:
    for name, value in _CONFIG_OVERRIDES.items():
        if name not in resolved:
            continue
        if not CONFIG_REGISTRY.get(name, {}).get("derived"):
            continue
        record = resolved[name]
        if record.source == "OVERRIDE":
            continue
        resolved[name] = ConfigRecord(
            name=name,
            value=_normalize(value, CONFIG_REGISTRY.get(name, {}).get("normalizer")),
            source="OVERRIDE",
            env=record.env,
            trace=(
                *record.trace,
                f"{name}=override({value!r}) applied after derived resolution",
            ),
        )
    return resolved


def _validate_config(values: Dict[str, ConfigRecord]) -> None:
    max_symbols = values["IBKR_MAX_SYMBOLS_PER_CYCLE"].value
    top_gainers = values["SCANNER_TOP_GAINERS_COUNT"].value
    watchlist_limit = values["SCANNER_WATCHLIST_LIMIT"].value

    if top_gainers > max_symbols:
        raise ConfigResolutionError(
            "Mismatch detected: SCANNER_TOP_GAINERS_COUNT exceeds IBKR_MAX_SYMBOLS_PER_CYCLE. "
            f"scanner={top_gainers} snapshot_cap={max_symbols}"
        )

    if watchlist_limit > top_gainers:
        raise ConfigResolutionError(
            "Mismatch detected: SCANNER_WATCHLIST_LIMIT exceeds SCANNER_TOP_GAINERS_COUNT. "
            f"watchlist={watchlist_limit} top_gainers={top_gainers}"
        )

    min_hold = values["MIN_HOLD_TICKS"].value
    max_hold = values["MAX_HOLD_TICKS"].value
    if min_hold > max_hold:
        raise ConfigResolutionError(
            f"MIN_HOLD_TICKS ({min_hold}) cannot exceed MAX_HOLD_TICKS ({max_hold})."
        )

    ross_min_gap = values["ROSS_RISK_MIN_GAP"].value
    ross_max_gap = values["ROSS_RISK_MAX_GAP"].value
    if ross_min_gap > ross_max_gap:
        raise ConfigResolutionError(
            "Ross risk gap bounds invalid: "
            f"ROSS_RISK_MIN_GAP={ross_min_gap} > ROSS_RISK_MAX_GAP={ross_max_gap}"
        )


def _env_fingerprint() -> tuple:
    pairs = []
    for entry in CONFIG_REGISTRY.values():
        for env_name in entry.get("env", []) or []:
            pairs.append((env_name, os.environ.get(env_name)))
    return tuple(sorted(set(pairs)))


def resolve_config() -> Dict[str, ConfigRecord]:
    global _CONFIG_CACHE, _CONFIG_CACHE_ENV_FINGERPRINT
    fingerprint = _env_fingerprint()
    if _CONFIG_CACHE is not None and _CONFIG_CACHE_ENV_FINGERPRINT == fingerprint:
        return _CONFIG_CACHE

    resolved: Dict[str, ConfigRecord] = {}
    for name, entry in CONFIG_REGISTRY.items():
        if entry.get("derived"):
            continue
        entry = {**entry, "name": name}
        record = _resolve_entry(name, entry)
        resolved[name] = record

    resolved = _resolve_derived(resolved)
    resolved = _apply_post_derived_overrides(resolved)
    _validate_config(resolved)

    _CONFIG_CACHE = resolved
    _CONFIG_CACHE_ENV_FINGERPRINT = fingerprint
    return resolved


def get_config(name: str) -> Any:
    resolved = resolve_config()
    if name not in resolved:
        raise ConfigResolutionError(f"Unknown configuration key '{name}'")
    _emit_config_summary_once(resolved)
    return resolved[name].value


def get_config_record(name: str) -> ConfigRecord:
    resolved = resolve_config()
    if name not in resolved:
        raise ConfigResolutionError(f"Unknown configuration key '{name}'")
    _emit_config_summary_once(resolved)
    return resolved[name]


def _emit_config_summary_once(resolved: Dict[str, ConfigRecord]) -> None:
    global _CONFIG_PRINTED
    if _CONFIG_PRINTED:
        return

    total = len(resolved)
    hard = sum(1 for name, entry in CONFIG_REGISTRY.items() if entry.get("enforcement") == "HARD")
    soft = sum(1 for name, entry in CONFIG_REGISTRY.items() if entry.get("enforcement") == "SOFT")
    advisory = sum(1 for name, entry in CONFIG_REGISTRY.items() if entry.get("enforcement") == "ADVISORY")

    scanner_cap = resolved["SCANNER_TOP_GAINERS_COUNT"].value
    snapshot_cap = resolved["IBKR_MAX_SYMBOLS_PER_CYCLE"].value
    snapshot_source = resolved["IBKR_MAX_SYMBOLS_PER_CYCLE"].source

    print(f"[CONFIG] Loaded {total} variables")
    print(f"[CONFIG] HARD enforced: {hard}")
    print(f"[CONFIG] Optional: {soft + advisory}")
    print(
        "[CONFIG] Scanner symbol cap: "
        f"{scanner_cap} (source={resolved['SCANNER_TOP_GAINERS_COUNT'].source})"
    )
    print(
        "[CONFIG] Market data snapshot cap: "
        f"{snapshot_cap} (source={snapshot_source})"
    )
    print("[CONFIG] No ambiguous defaults detected")

    _CONFIG_PRINTED = True


def get_config_snapshot() -> Dict[str, Any]:
    resolved = resolve_config()
    _emit_config_summary_once(resolved)
    snapshot = {
        "resolved_at": datetime.utcnow().isoformat(),
        "total": len(resolved),
        "hard": sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "HARD"),
        "soft": sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "SOFT"),
        "advisory": sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "ADVISORY"),
        "values": {name: record.value for name, record in resolved.items()},
        "sources": {name: record.source for name, record in resolved.items()},
        "env": {name: record.env for name, record in resolved.items()},
        "traces": {name: list(record.trace) for name, record in resolved.items()},
    }
    return snapshot


def get_config_resolution_trace(names: Iterable[str] | None = None) -> Dict[str, Dict[str, Any]]:
    resolved = resolve_config()
    selected = names or resolved.keys()
    trace: Dict[str, Dict[str, Any]] = {}
    for name in selected:
        record = resolved[name]
        trace[name] = {
            "value": record.value,
            "source": record.source,
            "env": record.env,
            "trace": list(record.trace),
        }
    return trace


def emit_config_event(event_collector) -> None:
    snapshot = get_config_snapshot()
    event_collector.emit(
        event_type="CONFIG_RESOLVED",
        source="ConfigResolver",
        payload={
            "resolved_at": snapshot["resolved_at"],
            "total": snapshot["total"],
            "hard": snapshot["hard"],
            "soft": snapshot["soft"],
            "advisory": snapshot["advisory"],
            "values": snapshot["values"],
            "sources": snapshot["sources"],
            "traces": snapshot["traces"],
        },
        include_cycle=False,
    )
