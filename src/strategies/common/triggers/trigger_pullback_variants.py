"""Trigger evaluators for registered pullback continuation variants.

These evaluators only consume levels and confirmation facts produced by the
canonical setup family. They do not derive new thresholds from selection RVOL
or candle-shape heuristics.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None

def _read(item: Any, field: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field)
    return getattr(item, field, None)

def _coalesce_float(*values: Any) -> float | None:
    for value in values:
        normalized = _safe_float(value)
        if normalized is not None:
            return normalized
    return None

def _normalise_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"1", "true", "yes", "y"}:
            return True
        if normalised in {"0", "false", "no", "n"}:
            return False
    return bool(value)

def _metadata(data: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = data.get("metadata") or data.get("setup_metadata") or {}
    return metadata if isinstance(metadata, Mapping) else {}

def _metadata_bool(data: Mapping[str, Any], key: str) -> bool | None:
    if key in data:
        return _normalise_bool(data.get(key))
    metadata = _metadata(data)
    if key in metadata:
        return _normalise_bool(metadata.get(key))
    return None

def _base_payload(
    data: Mapping[str, Any],
    trigger_level: float | None,
    stop_level: float | None,
    invalidation_level: float | None,
) -> dict[str, Any]:
    metadata = _metadata(data)
    execution_mode = data.get("execution_refinement_mode") or data.get("trigger_mode")
    if execution_mode is None:
        execution_mode = metadata.get("execution_refinement_mode") or metadata.get("trigger_mode") or "NONE"
    return {
        "trigger_type": "PULLBACK_HIGH_BREAK",
        "trigger_price_reference": trigger_level,
        "invalidation_price_reference": invalidation_level,
        "trigger_level": trigger_level,
        "stop_level": stop_level,
        "execution_refinement_mode": execution_mode,
        "trigger_mode": execution_mode,
        "level_type": "PULLBACK_HIGH",
    }

def _emit(family: str, payload: dict[str, Any]) -> dict[str, Any]:
    print(f"[TRIGGER][{family}] state={payload['trigger_state']} reason={payload['trigger_reason']}")
    return payload

def _terminal(
    family: str,
    data: Mapping[str, Any],
    trigger_level: float | None,
    stop_level: float | None,
    invalidation_level: float | None,
    state: str,
    ready: bool,
    reason: str,
    flags: list[str],
) -> dict[str, Any]:
    payload = {
        **_base_payload(data, trigger_level, stop_level, invalidation_level),
        "trigger_state": state,
        "trigger_ready_now": ready,
        "trigger_reason": reason,
        "quality_flags": flags,
        "trigger_quality_flags": flags,
    }
    return _emit(family, payload)


def _evaluate_pullback_high_break(family: str, pattern_result: Any, inputs: Any) -> dict[str, Any]:
    data = pattern_result if isinstance(pattern_result, Mapping) else {}
    values = inputs if isinstance(inputs, Mapping) else {}
    metadata = _metadata(data)
    candles = list(values.get("candles") or [])

    trigger_level = _coalesce_float(
        data.get("trigger_level"),
        data.get("trigger_price_reference"),
        metadata.get("trigger_level"),
        metadata.get("pullback_high"),
    )
    stop_level = _coalesce_float(data.get("stop_level"), metadata.get("stop_level"), metadata.get("pullback_low"))
    invalidation_level = _coalesce_float(
        data.get("invalidation_level"),
        data.get("invalidation_price_reference"),
        metadata.get("invalidation_level"),
        metadata.get("pullback_low"),
        stop_level,
    )

    if len(candles) < 2:
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "BLOCKED",
            False,
            "missing_candles",
            ["BLOCKED", "PATTERN_STRUCTURE_MISSING"],
        )
    if trigger_level is None or stop_level is None or invalidation_level is None:
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "BLOCKED",
            False,
            "missing_fields",
            ["BLOCKED", "PATTERN_STRUCTURE_MISSING"],
        )

    prev = candles[-2]
    last = candles[-1]
    prev_close = _safe_float(_read(prev, "close"))
    last_close = _safe_float(_read(last, "close"))
    last_high = _safe_float(_read(last, "high"))
    last_low = _safe_float(_read(last, "low"))
    if None in {prev_close, last_close, last_high, last_low}:
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "BLOCKED",
            False,
            "missing_price_fields",
            ["BLOCKED", "PATTERN_STRUCTURE_MISSING"],
        )

    invalidated = last_low <= invalidation_level or _metadata_bool(data, "structural_invalidation_breached") is True
    if invalidated:
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "BLOCKED",
            False,
            "structural_invalidation_breached",
            ["BLOCKED", "TRIGGER_INVALIDATED"],
        )

    breakout = prev_close <= trigger_level and last_close > trigger_level and last_high >= trigger_level
    if not breakout:
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "ARMED",
            False,
            "awaiting_pullback_break",
            ["ARMED_WAITING"],
        )

    volume_confirmation = _metadata_bool(data, "breakout_volume_confirmed")
    if volume_confirmation is not True:
        if volume_confirmation is False:
            reason = "breakout_volume_confirmation_failed"
            volume_flag = "PATTERN_VOLUME_CONFIRMATION_FAILED"
        else:
            reason = "breakout_volume_confirmation_missing"
            volume_flag = "PATTERN_VOLUME_CONFIRMATION_MISSING"
        return _terminal(
            family,
            data,
            trigger_level,
            stop_level,
            invalidation_level,
            "BLOCKED",
            False,
            reason,
            ["BLOCKED", volume_flag],
        )

    return _terminal(
        family,
        data,
        trigger_level,
        stop_level,
        invalidation_level,
        "FIRED",
        True,
        "pullback_high_broken",
        ["PULLBACK_HIGH_BREAK"],
    )

def evaluate_three_bar_pullback_trigger(pattern_result: Any, inputs: Any) -> dict[str, Any]:
    return _evaluate_pullback_high_break("THREE_BAR_PULLBACK", pattern_result, inputs)

def evaluate_second_pullback_trigger(pattern_result: Any, inputs: Any) -> dict[str, Any]:
    return _evaluate_pullback_high_break("SECOND_PULLBACK", pattern_result, inputs)
