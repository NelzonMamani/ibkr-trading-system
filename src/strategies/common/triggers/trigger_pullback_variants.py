"""Trigger evaluators for registered pullback continuation variants.

These evaluators only consume levels and confirmation facts produced by the
canonical setup family. They do not derive new thresholds from selection RVOL
or candle-shape heuristics.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from datetime import datetime, timedelta, timezone
from math import isfinite

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


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def _execution_evidence(data: Mapping[str, Any], candles: list) -> tuple[dict, str | None]:
    """Use the existing current-volume > mean-pullback-volume rule in one stream.

    Structural timestamps delimit the pullback; no primary bar volume or RVOL
    participates in execution confirmation. Candle timestamps denote bar starts.
    """
    evidence = dict(data["execution_stream"])
    metadata = _metadata(data)
    timeframe = evidence.get("execution_trigger_timeframe")
    seconds = {"10s": 10, "1m": 60, "5m": 300}.get(timeframe)
    if not seconds:
        return evidence, "execution_timeframe_unsupported"
    if evidence.get("stream_provenance") != "PRESENT":
        return evidence, "execution_stream_" + str(evidence.get("stream_provenance", "missing")).lower()
    if evidence.get("policy_action") == "BLOCK":
        return evidence, "execution_stream_policy_blocked"
    if len(candles) < 2:
        return evidence, "execution_stream_insufficient"
    times = [_timestamp(_read(c, "timestamp")) for c in candles]
    if any(t is None for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        return evidence, "execution_stream_malformed_timestamps"
    evidence.update(
        first_candle_timestamp=times[0].isoformat(),
        last_candle_timestamp=times[-1].isoformat(),
        candle_count=len(candles),
    )
    for candle in candles:
        values = [_safe_float(_read(candle, key)) for key in ("open", "high", "low", "close", "volume")]
        if any(v is None or not isfinite(v) for v in values):
            return evidence, "execution_stream_malformed_candle"
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c) or h < l:
            return evidence, "execution_stream_malformed_candle"
    start = _timestamp(metadata.get("pullback_start_timestamp"))
    end = _timestamp(metadata.get("pullback_end_timestamp"))
    if start is None or end is None or start >= end:
        return evidence, "execution_volume_structure_window_missing"
    baseline = [(t, c) for t, c in zip(times, candles) if start <= t < end]
    step = timedelta(seconds=seconds)
    if (not baseline or baseline[0][0] != start or baseline[-1][0] + step != end
            or any(b[0] - a[0] != step for a, b in zip(baseline, baseline[1:]))):
        return evidence, "execution_volume_history_missing"
    if times[-1] < end or times[-1] - times[-2] != step:
        return evidence, "execution_stream_insufficient"
    average = sum(float(_read(c, "volume")) for _, c in baseline) / len(baseline)
    if average <= 0:
        return evidence, "execution_volume_confirmation_missing"
    evidence.update(
        volume_baseline=average,
        volume_baseline_candle_count=len(baseline),
        volume_baseline_start=start.isoformat(),
        volume_baseline_end=end.isoformat(),
        current_volume=float(_read(candles[-1], "volume")),
        breakout_volume_confirmed=float(_read(candles[-1], "volume")) > average,
    )
    # An execution invalidation or consumed breakout remains terminal for this
    # originating structure, even when the primary candle has not advanced yet.
    level = _coalesce_float(data.get("trigger_level"), metadata.get("pullback_high"))
    stop = _coalesce_float(data.get("invalidation_level"), metadata.get("pullback_low"))
    for index, (timestamp, candle) in enumerate(zip(times, candles)):
        if timestamp < end:
            continue
        if index == 0 or timestamp - times[index - 1] != step:
            return evidence, "execution_stream_history_missing"
        if stop is not None and float(_read(candle, "low")) <= stop:
            return evidence, "structural_invalidation_breached"
        if (index < len(candles) - 1 and level is not None
                and float(_read(candles[index - 1], "close")) <= level
                and float(_read(candle, "close")) > level
                and float(_read(candle, "volume")) > average):
            return evidence, "pullback_breakout_already_consumed"
    return evidence, None


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
        **({"execution_stream": dict(data["execution_stream"])} if "execution_stream" in data else {}),
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

    if "execution_stream" in data:
        evidence, blocked_reason = _execution_evidence(data, candles)
        data = {**data, "execution_stream": evidence}
        if blocked_reason:
            return _terminal(
                family, data, trigger_level, stop_level, invalidation_level,
                "BLOCKED", False, blocked_reason, ["BLOCKED", "EXECUTION_STREAM_BLOCKED"],
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

    volume_confirmation = (
        data["execution_stream"].get("breakout_volume_confirmed")
        if "execution_stream" in data else _metadata_bool(data, "breakout_volume_confirmed")
    )
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
