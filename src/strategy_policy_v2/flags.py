from __future__ import annotations

from src.config.config_resolver import get_config


def is_policy_v2_enabled_globally() -> bool:
    raw = get_config("STRATEGY_POLICY_V2_ENABLED")
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_policy_v2_enabled_for_strategy(strategy_key: str) -> bool:
    if not is_policy_v2_enabled_globally():
        return False

    normalized = str(strategy_key or "").strip().lower()
    allowlist_raw = get_config("STRATEGY_POLICY_V2_STRATEGIES")
    if not isinstance(allowlist_raw, dict):
        return False

    for key, enabled in allowlist_raw.items():
        if str(key or "").strip().lower() == normalized:
            if isinstance(enabled, bool):
                return enabled
            return str(enabled).strip().lower() in {"1", "true", "yes", "on"}
    return False
