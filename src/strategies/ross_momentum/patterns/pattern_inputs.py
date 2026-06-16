"""Pattern input schema and builder for Ross Momentum patterns."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Dict, List, Optional

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.policy.pattern_input_policy import (
    IndicatorProvenance,
    MissingDataBehavior,
    PatternInputPolicy,
)
from src.strategies.strategy_contracts import SessionContext


_INDICATOR_NAMES = (
    "vwap",
    "ema9",
    "ema20",
    "ema200",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "volume",
    "rvol",
)


@dataclass(frozen=True)
class IndicatorSet:
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    vwap: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    ema9_prev: Optional[float] = None
    ema20_prev: Optional[float] = None


@dataclass(frozen=True)
class LevelSet:
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    hod: Optional[float] = None
    hod_source: Optional[str] = None
    lod: Optional[float] = None
    prior_close: Optional[float] = None
    vwap: Optional[float] = None
    support_levels: tuple[float, ...] = ()
    resistance_levels: tuple[float, ...] = ()
    key_levels: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LiquidityContext:
    spread: Optional[float]
    float_millions: Optional[float] = None
    rvol: Optional[float] = None
    volume: Optional[float] = None


@dataclass(frozen=True)
class PatternInputs:
    symbol: str
    timeframe: str
    candles: List[Candle]
    session_context: SessionContext
    levels: LevelSet
    indicators: IndicatorSet
    liquidity_context: LiquidityContext
    news_context: Optional[Dict[str, str]] = None
    data_quality_flags: List[str] = field(default_factory=list)
    timeframe_candles: Dict[str, List[Candle]] = field(default_factory=dict)
    primary_timeframe: str = "1m"
    execution_refinement_timeframe: str = "10s"
    context_timeframe: str = "5m"
    session_label: str = ""
    session_phase: Optional[str] = None
    timeframe_provenance: Dict[str, str] = field(default_factory=dict)
    indicator_provenance: Dict[str, str] = field(default_factory=dict)
    level_provenance: Dict[str, str] = field(default_factory=dict)
    setup_quality: Dict[str, Dict[str, object]] = field(default_factory=dict)
    missing_data_actions: Dict[str, str] = field(default_factory=dict)


def build_authoritative_pattern_inputs(
    *,
    symbol: str,
    session_label: str,
    timeframe_candles: Dict[str, List[Candle]] | None,
    indicators: IndicatorSet | None = None,
    levels: LevelSet | None = None,
    liquidity_context: LiquidityContext | None = None,
    news_context: Optional[Dict[str, str]] = None,
    policy: PatternInputPolicy | None = None,
    session_phase: str | None = None,
    now: datetime | None = None,
) -> PatternInputs:
    policy = policy or PatternInputPolicy.from_policy_v2()
    plan = policy.plan_for_session(session_label)
    now_utc = _coerce_utc(now) if now is not None else None
    normalized_candles = {
        _canonical_timeframe(name): _normalize_candle_timestamps(
            list(candles or []),
            symbol=symbol,
            timeframe=_canonical_timeframe(name),
        )
        for name, candles in (timeframe_candles or {}).items()
    }
    timeframe_provenance = {
        timeframe: _timeframe_provenance(
            normalized_candles.get(timeframe, []),
            timeframe,
            policy,
            symbol=symbol,
            now_utc=now_utc,
        )
        for timeframe in policy.preferred_timeframes
    }
    primary_timeframe = _canonical_timeframe(plan.primary_timeframe)
    primary_candles = normalized_candles.get(primary_timeframe, [])
    computed_indicators, indicator_provenance = _resolve_indicators(
        indicators,
        primary_candles,
        timeframe_status=timeframe_provenance.get(primary_timeframe, IndicatorProvenance.MISSING.value),
        liquidity_context=liquidity_context,
    )
    resolved_levels, level_provenance = _resolve_levels(
        levels,
        normalized_candles,
        computed_indicators,
    )
    resolved_liquidity = liquidity_context or LiquidityContext(spread=None)
    setup_quality, missing_data_actions = _evaluate_setup_quality(
        policy=policy,
        active_timeframes=tuple(dict.fromkeys(plan.required_timeframes + plan.preferred_timeframes)),
        timeframe_provenance=timeframe_provenance,
        indicator_provenance=indicator_provenance,
        level_provenance=level_provenance,
    )
    data_quality_flags = _data_quality_flags(setup_quality)
    session_context = _session_context_for(session_label)
    print(
        "[ROSS][PATTERN_INPUT][BUILD] "
        f"symbol={symbol} session={session_label} primary={primary_timeframe} "
        f"execution={_canonical_timeframe(plan.execution_refinement_timeframe)} context={_canonical_timeframe(plan.context_timeframe)}"
    )
    print(
        "[ROSS][PATTERN_INPUT][TIMEFRAMES] "
        f"symbol={symbol} status={_compact_mapping(timeframe_provenance)} "
        f"counts={{{', '.join(f'{key}:{len(value)}' for key, value in sorted(normalized_candles.items()))}}}"
    )
    print(
        "[ROSS][PATTERN_INPUT][INDICATORS] "
        f"symbol={symbol} provenance={_compact_mapping(indicator_provenance)}"
    )
    print(
        "[ROSS][PATTERN_INPUT][LEVELS] "
        f"symbol={symbol} provenance={_compact_mapping(level_provenance)}"
    )
    print(
        "[ROSS][PATTERN_INPUT][MISSING] "
        f"symbol={symbol} actions={_compact_mapping(missing_data_actions)}"
    )
    print(
        "[ROSS][PATTERN_INPUT][QUALITY] "
        f"symbol={symbol} blocked={_setups_with_action(setup_quality, MissingDataBehavior.BLOCK)} "
        f"degraded={_setups_with_action(setup_quality, MissingDataBehavior.DEGRADE)} "
        f"warn={_setups_with_action(setup_quality, MissingDataBehavior.WARN)}"
    )
    return PatternInputs(
        symbol=symbol,
        timeframe=primary_timeframe,
        candles=primary_candles,
        session_context=session_context,
        levels=resolved_levels,
        indicators=computed_indicators,
        liquidity_context=resolved_liquidity,
        news_context=dict(news_context or {}),
        data_quality_flags=data_quality_flags,
        timeframe_candles=normalized_candles,
        primary_timeframe=primary_timeframe,
        execution_refinement_timeframe=_canonical_timeframe(plan.execution_refinement_timeframe),
        context_timeframe=_canonical_timeframe(plan.context_timeframe),
        session_label=session_label,
        session_phase=session_phase or session_label,
        timeframe_provenance=timeframe_provenance,
        indicator_provenance=indicator_provenance,
        level_provenance=level_provenance,
        setup_quality=setup_quality,
        missing_data_actions=missing_data_actions,
    )


def _canonical_timeframe(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "s10": "10s",
        "10s": "10s",
        "10sec": "10s",
        "10second": "10s",
        "m1": "1m",
        "1m": "1m",
        "1min": "1m",
        "1minute": "1m",
        "m5": "5m",
        "5m": "5m",
        "5min": "5m",
        "5minute": "5m",
    }
    return aliases.get(text, text or "1m")


def _timeframe_provenance(
    candles: List[Candle],
    timeframe: str,
    policy: PatternInputPolicy,
    *,
    symbol: str | None = None,
    now_utc: datetime | None,
) -> str:
    if not candles:
        return IndicatorProvenance.MISSING.value
    latest_timestamp = max(
        (_coerce_utc(candle.timestamp) for candle in candles if candle.timestamp is not None),
        default=None,
    )
    if latest_timestamp is None and now_utc is not None:
        print(
            "[ROSS][RUNTIME_FIX][PATTERN_INPUT_UNAVAILABLE] "
            f"symbol={symbol or 'UNKNOWN'} timeframe={timeframe} status=STALE reason=timestamp_unavailable"
        )
        return IndicatorProvenance.STALE.value
    if latest_timestamp is not None and now_utc is not None:
        age_seconds = (now_utc - latest_timestamp).total_seconds()
        if age_seconds > policy.candle_freshness_seconds.get(timeframe, 300):
            return IndicatorProvenance.STALE.value
    return IndicatorProvenance.PRESENT.value


def _resolve_indicators(
    provided: IndicatorSet | None,
    candles: List[Candle],
    *,
    timeframe_status: str,
    liquidity_context: LiquidityContext | None,
) -> tuple[IndicatorSet, Dict[str, str]]:
    provided = provided or IndicatorSet()
    closes = [float(candle.close) for candle in candles]
    unavailable = timeframe_status in {IndicatorProvenance.MISSING.value, IndicatorProvenance.STALE.value}
    values: dict[str, float | None] = {}
    provenance: dict[str, str] = {}

    for name in ("vwap", "ema9", "ema20", "ema200"):
        explicit = getattr(provided, name)
        if explicit is not None:
            values[name] = float(explicit)
            provenance[name] = IndicatorProvenance.PRESENT.value
            continue
        if unavailable:
            values[name] = None
            provenance[name] = IndicatorProvenance.UNAVAILABLE_FOR_TIMEFRAME.value
            continue
        computed = (
            _vwap(candles)
            if name == "vwap"
            else _ema(closes, 9)
            if name == "ema9"
            else _ema(closes, 20)
            if name == "ema20"
            else _ema(closes, 200) if len(closes) >= 200 else None
        )
        values[name] = computed
        provenance[name] = IndicatorProvenance.COMPUTED.value if computed is not None else IndicatorProvenance.MISSING.value

    macd = _macd(closes) if not unavailable else None
    for name, index in (("macd_line", 0), ("macd_signal", 1), ("macd_histogram", 2)):
        explicit = getattr(provided, name)
        if explicit is not None:
            values[name] = float(explicit)
            provenance[name] = IndicatorProvenance.PRESENT.value
        elif unavailable:
            values[name] = None
            provenance[name] = IndicatorProvenance.UNAVAILABLE_FOR_TIMEFRAME.value
        elif macd is not None:
            values[name] = macd[index]
            provenance[name] = IndicatorProvenance.COMPUTED.value
        else:
            values[name] = None
            provenance[name] = IndicatorProvenance.MISSING.value

    provenance["volume"] = IndicatorProvenance.PRESENT.value if candles else IndicatorProvenance.MISSING.value
    provenance["rvol"] = (
        IndicatorProvenance.PRESENT.value
        if liquidity_context is not None and liquidity_context.rvol is not None
        else IndicatorProvenance.MISSING.value
    )
    return (
        replace(
            provided,
            vwap=values["vwap"],
            ema9=values["ema9"],
            ema20=values["ema20"],
            ema200=values["ema200"],
            macd_line=values["macd_line"],
            macd_signal=values["macd_signal"],
            macd_histogram=values["macd_histogram"],
        ),
        provenance,
    )


def _resolve_levels(
    provided: LevelSet | None,
    timeframe_candles: Dict[str, List[Candle]],
    indicators: IndicatorSet,
) -> tuple[LevelSet, Dict[str, str]]:
    provided = provided or LevelSet()
    all_candles = [
        candle
        for timeframe in ("10s", "1m", "5m")
        for candle in timeframe_candles.get(timeframe, [])
    ]
    highs = [float(candle.high) for candle in all_candles]
    lows = [float(candle.low) for candle in all_candles]
    premarket_high = provided.premarket_high
    premarket_low = provided.premarket_low
    hod = provided.hod if provided.hod is not None else (max(highs) if highs else None)
    lod = provided.lod if provided.lod is not None else (min(lows) if lows else None)
    vwap = provided.vwap if provided.vwap is not None else indicators.vwap
    key_levels = dict(provided.key_levels or {})
    for key, value in {
        "PREMARKET_HIGH": premarket_high,
        "PREMARKET_LOW": premarket_low,
        "HOD": hod,
        "LOD": lod,
        "PRIOR_CLOSE": provided.prior_close,
        "VWAP": vwap,
    }.items():
        if value is not None:
            key_levels.setdefault(key, float(value))
    resolved = replace(
        provided,
        hod=hod,
        lod=lod,
        vwap=vwap,
        key_levels=key_levels,
    )
    provenance = {
        "premarket_high": _level_provenance(provided.premarket_high, "PRESENT"),
        "premarket_low": _level_provenance(provided.premarket_low, "PRESENT"),
        "hod": _level_provenance(hod, "COMPUTED" if provided.hod is None else "PRESENT"),
        "lod": _level_provenance(lod, "COMPUTED" if provided.lod is None else "PRESENT"),
        "prior_close": _level_provenance(provided.prior_close, "PRESENT"),
        "vwap": _level_provenance(vwap, "COMPUTED" if provided.vwap is None else "PRESENT"),
        "support_levels": IndicatorProvenance.PRESENT.value if provided.support_levels else IndicatorProvenance.MISSING.value,
        "resistance_levels": IndicatorProvenance.PRESENT.value if provided.resistance_levels else IndicatorProvenance.MISSING.value,
    }
    return resolved, provenance


def _evaluate_setup_quality(
    *,
    policy: PatternInputPolicy,
    active_timeframes: tuple[str, ...],
    timeframe_provenance: Dict[str, str],
    indicator_provenance: Dict[str, str],
    level_provenance: Dict[str, str],
) -> tuple[Dict[str, Dict[str, object]], Dict[str, str]]:
    setup_quality: dict[str, dict[str, object]] = {}
    missing_actions: dict[str, str] = {}
    severity = {
        MissingDataBehavior.IGNORE: 0,
        MissingDataBehavior.WARN: 1,
        MissingDataBehavior.DEGRADE: 2,
        MissingDataBehavior.BLOCK: 3,
    }
    for setup, requirement in policy.setup_family_requirements.items():
        findings: list[dict[str, str]] = []
        setup_indicator_provenance: dict[str, str] = {}
        active_timeframe_set = set(active_timeframes)
        for timeframe in requirement.required_timeframes + requirement.preferred_timeframes:
            if timeframe not in active_timeframe_set:
                continue
            item = f"timeframe:{timeframe}"
            status = timeframe_provenance.get(timeframe, IndicatorProvenance.MISSING.value)
            if status not in {IndicatorProvenance.PRESENT.value, IndicatorProvenance.COMPUTED.value}:
                behavior = requirement.behavior_for(item)
                if timeframe in requirement.required_timeframes and behavior == MissingDataBehavior.IGNORE:
                    behavior = MissingDataBehavior.BLOCK
                findings.append({"item": item, "provenance": status, "behavior": behavior.value})
                _raise_missing_action(missing_actions, item, behavior, severity)
        for indicator in _INDICATOR_NAMES:
            status = indicator_provenance.get(indicator, IndicatorProvenance.MISSING.value)
            if indicator in requirement.required_indicators:
                setup_indicator_provenance[indicator] = status
                if status not in {IndicatorProvenance.PRESENT.value, IndicatorProvenance.COMPUTED.value}:
                    behavior = requirement.behavior_for(indicator)
                    if behavior == MissingDataBehavior.IGNORE:
                        behavior = MissingDataBehavior.BLOCK
                    findings.append({"item": indicator, "provenance": status, "behavior": behavior.value})
                    _raise_missing_action(missing_actions, indicator, behavior, severity)
            elif indicator in requirement.optional_indicators:
                behavior = requirement.behavior_for(indicator)
                setup_indicator_provenance[indicator] = (
                    IndicatorProvenance.NOT_REQUIRED_FOR_SETUP.value
                    if status in {IndicatorProvenance.MISSING.value, IndicatorProvenance.UNAVAILABLE_FOR_TIMEFRAME.value}
                    and behavior == MissingDataBehavior.IGNORE
                    else status
                )
                if status not in {IndicatorProvenance.PRESENT.value, IndicatorProvenance.COMPUTED.value} and behavior != MissingDataBehavior.IGNORE:
                    findings.append({"item": indicator, "provenance": status, "behavior": behavior.value})
                    _raise_missing_action(missing_actions, indicator, behavior, severity)
            else:
                setup_indicator_provenance[indicator] = IndicatorProvenance.NOT_REQUIRED_FOR_SETUP.value
        for level in requirement.required_levels + requirement.optional_levels:
            status = level_provenance.get(level, IndicatorProvenance.MISSING.value)
            if status not in {IndicatorProvenance.PRESENT.value, IndicatorProvenance.COMPUTED.value}:
                behavior = requirement.behavior_for(level)
                if level in requirement.required_levels and behavior == MissingDataBehavior.IGNORE:
                    behavior = MissingDataBehavior.BLOCK
                findings.append({"item": level, "provenance": status, "behavior": behavior.value})
                _raise_missing_action(missing_actions, level, behavior, severity)
        action = max(
            (MissingDataBehavior(finding["behavior"]) for finding in findings),
            key=lambda value: severity[value],
            default=MissingDataBehavior.IGNORE,
        )
        setup_quality[setup] = {
            "action": action.value,
            "missing": findings,
            "indicator_provenance": setup_indicator_provenance,
            "required_timeframes": list(requirement.required_timeframes),
            "preferred_timeframes": list(requirement.preferred_timeframes),
        }
    return setup_quality, missing_actions


def _raise_missing_action(
    actions: Dict[str, str],
    item: str,
    behavior: MissingDataBehavior,
    severity: Dict[MissingDataBehavior, int],
) -> None:
    current = MissingDataBehavior(actions[item]) if item in actions else MissingDataBehavior.IGNORE
    if severity[behavior] > severity[current]:
        actions[item] = behavior.value


def _data_quality_flags(setup_quality: Dict[str, Dict[str, object]]) -> List[str]:
    flags: set[str] = set()
    for setup, quality in setup_quality.items():
        action = str(quality.get("action") or "")
        if action in {"BLOCK", "DEGRADE", "WARN"}:
            flags.add(f"PATTERN_INPUT_{action}_{setup}")
    return sorted(flags)


def _setups_with_action(setup_quality: Dict[str, Dict[str, object]], action: MissingDataBehavior) -> list[str]:
    return sorted(setup for setup, quality in setup_quality.items() if quality.get("action") == action.value)


def _level_provenance(value: float | None, source: str) -> str:
    if value is None:
        return IndicatorProvenance.MISSING.value
    if source == "COMPUTED":
        return IndicatorProvenance.COMPUTED.value
    return IndicatorProvenance.PRESENT.value


def _ema(closes: List[float], period: int) -> Optional[float]:
    if not closes:
        return None
    multiplier = 2.0 / (period + 1)
    ema_value = float(closes[0])
    for close in closes[1:]:
        ema_value = (float(close) * multiplier) + (ema_value * (1.0 - multiplier))
    return round(ema_value, 6)


def _vwap(candles: List[Candle]) -> Optional[float]:
    total_pv = 0.0
    total_volume = 0.0
    for candle in candles:
        volume = float(candle.volume or 0.0)
        typical = (float(candle.high) + float(candle.low) + float(candle.close)) / 3.0
        total_pv += typical * volume
        total_volume += volume
    if total_volume <= 0:
        return None
    return round(total_pv / total_volume, 6)


def _macd(closes: List[float]) -> tuple[float, float, float] | None:
    if len(closes) < 26:
        return None
    line = (_ema(closes, 12) or 0.0) - (_ema(closes, 26) or 0.0)
    line_series: list[float] = []
    for idx in range(26, len(closes) + 1):
        window = closes[:idx]
        line_series.append((_ema(window, 12) or 0.0) - (_ema(window, 26) or 0.0))
    signal = _ema(line_series, 9) if line_series else None
    if signal is None:
        return None
    hist = line - signal
    return round(line, 6), round(signal, 6), round(hist, 6)


def _session_context_for(session_label: str | None) -> SessionContext:
    session = str(session_label or "").strip().upper()
    if session in {"AH", "AFTER", "AFTER_HOURS"}:
        return SessionContext.AFTER
    if session in {"RTH", "REG", "REGULAR", "RTH_OPEN", "RTH_MID", "RTH_LATE", "MIDDAY", "LATE", "POWER_HOUR"}:
        return SessionContext.REGULAR
    return SessionContext.PRE


def _normalize_candle_timestamps(
    candles: List[Candle],
    *,
    symbol: str,
    timeframe: str,
) -> List[Candle]:
    normalized: list[Candle] = []
    for candle in candles:
        raw_timestamp = getattr(candle, "timestamp", None)
        if raw_timestamp is None:
            normalized.append(candle)
            continue
        try:
            timestamp = normalize_timestamp_utc(
                raw_timestamp,
                symbol=symbol,
                timeframe=timeframe,
            )
        except ValueError as exc:
            print(
                "[ROSS][RUNTIME_FIX][PATTERN_INPUT_UNAVAILABLE] "
                f"symbol={symbol} timeframe={timeframe} status=STALE reason={exc}"
            )
            normalized.append(replace(candle, timestamp=None))
            continue
        normalized.append(replace(candle, timestamp=timestamp))
    return normalized


def normalize_timestamp_utc(
    value: Any,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    emit_log: bool = True,
) -> datetime:
    source_type = type(value).__name__
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        _log_timestamp_normalized(
            value=value,
            normalized=normalized,
            source_type=source_type,
            symbol=symbol,
            timeframe=timeframe,
            emit_log=emit_log and (value.tzinfo is None or normalized != value),
        )
        return normalized

    if isinstance(value, str):
        normalized = _parse_timestamp_string(value)
        _log_timestamp_normalized(
            value=value,
            normalized=normalized,
            source_type=source_type,
            symbol=symbol,
            timeframe=timeframe,
            emit_log=emit_log,
        )
        return normalized

    raise ValueError(f"unsupported_timestamp_type:{source_type}")


def _parse_timestamp_string(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("unsupported_timestamp_format:empty")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    parts = text.split()
    timezone_name: str | None = None
    core = text
    if len(parts) >= 3 and "/" in parts[-1]:
        timezone_name = parts[-1]
        core = " ".join(parts[:-1])
    elif len(parts) >= 3 and parts[-1].upper() in {"UTC", "GMT"}:
        timezone_name = "UTC"
        core = " ".join(parts[:-1])

    for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d-%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(core, fmt)
            tz = _zoneinfo_or_utc(timezone_name)
            return parsed.replace(tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unsupported_timestamp_format:{value}")


def _zoneinfo_or_utc(timezone_name: str | None):
    if not timezone_name:
        return timezone.utc
    if timezone_name.upper() in {"UTC", "GMT"}:
        return timezone.utc
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unsupported_timestamp_timezone:{timezone_name}") from exc


def _log_timestamp_normalized(
    *,
    value: Any,
    normalized: datetime,
    source_type: str,
    symbol: str | None,
    timeframe: str | None,
    emit_log: bool,
) -> None:
    if not emit_log:
        return
    print(
        "[ROSS][RUNTIME_FIX][TIMESTAMP_NORMALIZED] "
        f"symbol={symbol or 'UNKNOWN'} timeframe={timeframe or 'UNKNOWN'} "
        f"source_type={source_type} normalized={normalized.isoformat()}"
    )


def _coerce_utc(value: Any) -> datetime:
    return normalize_timestamp_utc(value, emit_log=False)


def _compact_mapping(mapping: Dict[str, Any]) -> str:
    return ",".join(f"{key}={mapping[key]}" for key in sorted(mapping)) or "none"
