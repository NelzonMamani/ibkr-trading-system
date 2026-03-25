from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from src.adapters.data import historical_data_provider
from src.adapters.data.historical_data_provider import get_intraday_bars
from src.data.fundamentals.float_provider import FloatProvider
from src.domain.market_snapshot import MarketSnapshot
from src.scanner.session_pct_change import compute_session_relative_volume_with_provenance, normalize_session_label
from src.scanner.result_models import CandidateMetrics
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.strategy_contracts import SessionContext

# Restore test monkeypatch compatibility
historical_data_provider.get_intraday_bars = get_intraday_bars
_PRE_VOLUME_MIN = 10_000.0
_RTH_VOLUME_MIN = 50_000.0
_PRE_RVOL_MIN = 0.8
_RTH_RVOL_MIN = 1.5


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return getattr(value, "value")
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(v) for v in value]
    return value


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    multiplier = 2.0 / (period + 1)
    ema_value = float(values[0])
    for price in values[1:]:
        ema_value = (float(price) * multiplier) + (ema_value * (1.0 - multiplier))
    return round(ema_value, 6)


def _vwap(candles: list[Candle]) -> float | None:
    total_pv = 0.0
    total_volume = 0.0
    for candle in candles:
        volume = _safe_float(candle.volume) or 0.0
        typical_price = ((_safe_float(candle.high) or 0.0) + (_safe_float(candle.low) or 0.0) + (_safe_float(candle.close) or 0.0)) / 3.0
        total_pv += typical_price * volume
        total_volume += volume
    if total_volume <= 0:
        return None
    return round(total_pv / total_volume, 6)


def _timestamp_as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_premarket_candle(candle: Candle) -> bool:
    timestamp = _timestamp_as_utc(getattr(candle, "timestamp", None))
    if timestamp is None:
        return False
    market_open_utc = time(14, 30)
    return timestamp.time() < market_open_utc


def _infer_reference_price(*, row: Any, candles: list[Candle], session: str, prior_close: float | None) -> float | None:
    if session == "PRE":
        return _coalesce(
            prior_close,
            _safe_float(_get_value(row, "reference_price")),
            _safe_float(_get_value(row, "prev_close")),
            _safe_float(_get_value(row, "close")),
        )
    first_regular_candle = next((c for c in candles if not _is_premarket_candle(c)), None)
    return _coalesce(
        _safe_float(_get_value(row, "session_open")),
        _safe_float(_get_value(row, "open")),
        _safe_float(getattr(first_regular_candle, "open", None)),
        prior_close,
        _safe_float(_get_value(row, "reference_price")),
        _safe_float(_get_value(row, "prev_close")),
    )


def _rolling_rvol(*, total_volume: float | None, candles: list[Candle]) -> float | None:
    if total_volume is None or total_volume <= 0 or not candles:
        return None
    recent = candles[-20:]
    avg_volume_window = sum(max(_safe_float(c.volume) or 0.0, 0.0) for c in recent) / max(len(recent), 1)
    if avg_volume_window <= 0:
        return None
    return round(total_volume / avg_volume_window, 6)


def _session_thresholds(session: str) -> tuple[float, float]:
    if session == "PRE":
        return _PRE_VOLUME_MIN, _PRE_RVOL_MIN
    return _RTH_VOLUME_MIN, _RTH_RVOL_MIN


def _is_rth_session(session: str) -> bool:
    return session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REG", "REGULAR", "POWER_HOUR", "LATE"}


def _resolve_float_millions(symbol: str, row: Any, quality_flags: list[str]) -> float | None:
    existing_float = _coalesce(
        _safe_float(_get_value(row, "float_millions")),
        (_safe_float(_get_value(row, "float_shares")) or 0.0) / 1_000_000.0 if _get_value(row, "float_shares") is not None else None,
        (_safe_float(_get_value(row, "float_shares_raw")) or 0.0) / 1_000_000.0 if _get_value(row, "float_shares_raw") is not None else None,
    )
    if existing_float is not None:
        return round(existing_float, 6)
    try:
        float_shares, _source = FloatProvider().get_float(symbol)
    except Exception:
        float_shares = None
    if float_shares is None:
        quality_flags.append("float_missing")
        return None
    return round(float(float_shares) / 1_000_000.0, 6)


@dataclass
class PatternInputSnapshotSummary:
    candle_count: int
    last_price: float | None
    bid: float | None
    ask: float | None
    spread: float | None
    volume: float | None
    pct_change: float | None
    rvol: float | None
    float_millions: float | None
    has_levels: bool
    levels_present: list[str] = field(default_factory=list)
    has_indicators: bool = False
    indicators_present: list[str] = field(default_factory=list)
    session_context: str | None = None
    timeframe: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RossPatternTrace:
    symbol: str
    cycle_id: str | None
    strategy_key: str
    session_label: str | None
    session_phase: str | None
    runtime_mode: str | None
    symbol_source: str | None
    pattern_id: str
    pattern_name: str
    setup_family_id: str | None
    invoked: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    detected: bool = False
    rejection_reason: str | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)
    input_quality_flags: list[str] = field(default_factory=list)
    post_detect_disposition: str | None = None
    final_outcome: str | None = None
    exception: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RossSymbolTrace:
    symbol: str
    cycle_id: str | None
    strategy_key: str
    session_label: str | None
    session_phase: str | None
    runtime_mode: str | None
    symbol_source: str | None
    manual_focus: bool = False
    bypassed_watchlist: bool = False
    registry_path: str = "RossPatternRegistry"
    registry_matches_audit: bool = True
    input_summary: dict[str, Any] = field(default_factory=dict)
    pre_registry_failure_reason: str | None = None
    pattern_traces: list[RossPatternTrace] = field(default_factory=list)
    detected_pattern_ids: list[str] = field(default_factory=list)
    dropped_detected_pattern_ids: list[str] = field(default_factory=list)
    final_outcome: str | None = None
    synthetic_forced_intent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RossCycleTrace:
    cycle_id: str | None
    strategy_key: str
    session_label: str | None
    session_phase: str | None
    runtime_mode: str | None
    evaluated_count: int
    real_setup_trigger_count: int
    synthetic_forced_intents: int
    pattern_invocations_total: int
    patterns_detected_total: int
    dominant_skip_reasons: dict[str, int]
    dominant_rejection_reasons: dict[str, int]
    symbols_with_missing_inputs: list[str]
    symbols_with_detected_but_discarded: list[str]
    symbols_with_zero_pattern_invocations: list[str]
    symbols_failing_before_registry: list[str]
    symbols_failing_after_registry: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RossPatternFailureTraceCollector:
    def __init__(self, evidence_root: Path | None = None, max_cycles: int = 5) -> None:
        self.evidence_root = evidence_root or Path("AUDIT_EVIDENCE") / "p01_live_pattern_failure_trace"
        self.max_cycles = max_cycles
        self._cycles: list[RossCycleTrace] = []
        self._symbols: list[RossSymbolTrace] = []
        self._patterns: list[RossPatternTrace] = []

    def record_symbol(self, trace: RossSymbolTrace) -> None:
        self._symbols.append(trace)
        self._patterns.extend(trace.pattern_traces)

    def build_cycle_summary(
        self,
        *,
        cycle_id: str | None,
        strategy_key: str,
        session_label: str | None,
        session_phase: str | None,
        runtime_mode: str | None,
        symbol_traces: Iterable[RossSymbolTrace],
        real_setup_trigger_count: int,
        synthetic_forced_intents: int,
    ) -> RossCycleTrace:
        traces = list(symbol_traces)
        skip_counter = Counter()
        rejection_counter = Counter()
        missing_inputs = []
        detected_but_discarded = []
        zero_invocations = []
        before_registry = []
        after_registry = []
        invocations = 0
        detected_total = 0
        for trace in traces:
            if trace.pre_registry_failure_reason:
                before_registry.append(trace.symbol)
                missing_inputs.append(trace.symbol)
            if not trace.pattern_traces:
                zero_invocations.append(trace.symbol)
            if trace.detected_pattern_ids and trace.dropped_detected_pattern_ids:
                detected_but_discarded.append(trace.symbol)
            if trace.final_outcome and trace.final_outcome.startswith("NO_SETUP"):
                after_registry.append(trace.symbol)
            for pattern_trace in trace.pattern_traces:
                invocations += int(pattern_trace.invoked)
                detected_total += int(pattern_trace.detected)
                if pattern_trace.skip_reason:
                    skip_counter[pattern_trace.skip_reason] += 1
                if pattern_trace.rejection_reason:
                    rejection_counter[pattern_trace.rejection_reason] += 1
        cycle = RossCycleTrace(
            cycle_id=cycle_id,
            strategy_key=strategy_key,
            session_label=session_label,
            session_phase=session_phase,
            runtime_mode=runtime_mode,
            evaluated_count=len(traces),
            real_setup_trigger_count=real_setup_trigger_count,
            synthetic_forced_intents=synthetic_forced_intents,
            pattern_invocations_total=invocations,
            patterns_detected_total=detected_total,
            dominant_skip_reasons=dict(skip_counter.most_common(10)),
            dominant_rejection_reasons=dict(rejection_counter.most_common(10)),
            symbols_with_missing_inputs=sorted(set(missing_inputs)),
            symbols_with_detected_but_discarded=sorted(set(detected_but_discarded)),
            symbols_with_zero_pattern_invocations=sorted(set(zero_invocations)),
            symbols_failing_before_registry=sorted(set(before_registry)),
            symbols_failing_after_registry=sorted(set(after_registry)),
        )
        self._cycles.append(cycle)
        self._cycles = self._cycles[-self.max_cycles :]
        return cycle

    def persist_latest(self, *, run_mode: str | None, session_label: str | None, session_phase: str | None) -> Path:
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_mode": run_mode,
            "session_label": session_label,
            "session_phase": session_phase,
            "cycle_summaries": [cycle.to_dict() for cycle in self._cycles[-self.max_cycles :]],
            "symbol_evaluations": [trace.to_dict() for trace in self._symbols[-200 :]],
            "pattern_traces": [trace.to_dict() for trace in self._patterns[-1000 :]],
            "aggregated_failure_reasons": self._cycles[-1].to_dict() if self._cycles else {},
        }
        latest_path = self.evidence_root / "latest_pattern_failure_trace.json"
        latest_path.write_text(json.dumps(_serialize(payload), indent=2), encoding="utf-8")
        return latest_path


def _get_value(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def infer_symbol_source(row: Any) -> str:
    promotion_reason = str(_get_value(row, "promotion_reason") or "").lower()
    watchlist_source = str(_get_value(row, "watchlist_source") or "").lower()
    if promotion_reason == "manual_focus":
        return "manual_focus"
    if "manual" in watchlist_source:
        return "manual_focus"
    if promotion_reason:
        return promotion_reason
    if watchlist_source:
        return watchlist_source
    return "watchlist"


def build_input_snapshot_summary(*, row: Any, snapshot: MarketSnapshot | None, inputs: PatternInputs | None, session_label: str | None, quality_flags: list[str] | None = None) -> PatternInputSnapshotSummary:
    input_flags = list(getattr(inputs, "data_quality_flags", []) if inputs else [])
    bid = _safe_float(getattr(snapshot, "bid", None))
    ask = _safe_float(getattr(snapshot, "ask", None))
    last = _safe_float(getattr(snapshot, "last", None))
    row_last = _safe_float(_get_value(row, "last_price") or _get_value(row, "price"))
    volume = _safe_float(getattr(snapshot, "volume", None) or _get_value(row, "volume"))
    spread = _safe_float(_get_value(row, "spread"))
    if spread is None and bid is not None and ask is not None:
        spread = round(ask - bid, 4)
    levels_present = []
    indicators_present = []
    if inputs:
        levels_present = [name for name in ("premarket_high", "premarket_low", "hod", "lod", "prior_close") if getattr(inputs.levels, name, None) is not None]
        indicators_present = [name.upper() for name in ("ema9", "ema20", "vwap") if getattr(inputs.indicators, name, None) is not None]
    missing_fields = []
    for name, value in {
        "last_price": last if last is not None else row_last,
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "rvol": _coalesce(getattr(inputs.liquidity_context, "rvol", None) if inputs else None, _get_value(row, "rvol")),
        "float_millions": _coalesce(getattr(inputs.liquidity_context, "float_millions", None) if inputs else None, _get_value(row, "float_millions")),
    }.items():
        if value is None:
            missing_fields.append(name)
    candles = list(inputs.candles) if inputs else []
    return PatternInputSnapshotSummary(
        candle_count=len(candles),
        last_price=last if last is not None else row_last,
        bid=bid,
        ask=ask,
        spread=spread,
        volume=volume,
        pct_change=_coalesce(_safe_float((inputs.news_context or {}).get("pct_change")) if inputs and inputs.news_context else None, _safe_float(_get_value(row, "pct_change") or _get_value(row, "pct_change_resolved"))),
        rvol=_coalesce(_safe_float(getattr(inputs.liquidity_context, "rvol", None) if inputs else None), _safe_float(_get_value(row, "rvol") or _get_value(row, "relative_volume"))),
        float_millions=_coalesce(_safe_float(getattr(inputs.liquidity_context, "float_millions", None) if inputs else None), _safe_float(_get_value(row, "float_millions"))),
        has_levels=bool(levels_present),
        levels_present=levels_present,
        has_indicators=bool(indicators_present),
        indicators_present=indicators_present,
        session_context=getattr(inputs.session_context, "value", None) if inputs else session_label,
        timeframe=inputs.timeframe if inputs else None,
        quality_flags=sorted(set(list(quality_flags or []) + input_flags)),
        missing_fields=sorted(set(missing_fields)),
    )


def build_runtime_pattern_inputs(*, symbol: str, row: Any, snapshot: MarketSnapshot | None, session_label: str | None, session_phase: str | None) -> tuple[PatternInputs | None, list[str]]:
    quality_flags: list[str] = list(_get_value(row, "data_quality_flags") or [])
    last = _safe_float(getattr(snapshot, "last", None))
    bid = _safe_float(getattr(snapshot, "bid", None))
    ask = _safe_float(getattr(snapshot, "ask", None))
    volume = _safe_float(
        getattr(snapshot, "volume", None)
        or _get_value(row, "current_intraday_volume")
        or _get_value(row, "volume")
    )
    row_last = _safe_float(_get_value(row, "last_price") or _get_value(row, "price"))
    last_price = last if last is not None else row_last
    if last_price is None:
        quality_flags.append("missing_last_price")
    if volume is None:
        quality_flags.append("missing_volume")
    historical_data_provider.get_intraday_bars = get_intraday_bars
    intraday_bars = historical_data_provider.get_intraday_bars(
        symbol=symbol,
        timeframe="1m",
        limit=50,
    )

    if intraday_bars is None or len(intraday_bars) == 0:
        print(f"[PATTERN_INPUT][BLOCK] symbol={symbol} reason=insufficient_intraday_data")
        quality_flags.append("insufficient_intraday_data")
        return None, sorted(set(quality_flags))
    if len(intraday_bars) < 20:
        quality_flags.append("insufficient_candles")

    print(
        f"[INTRADAY_FETCH] symbol={symbol} candles={len(intraday_bars)} source=IBKR_INTRADAY"
    )

    candles: list[Candle] = intraday_bars

    def _normalize_bar(bar: Candle) -> Candle:
        bar_volume = _safe_float(getattr(bar, "volume", None))
        if bar_volume is None:
            bar_volume = _safe_float(getattr(bar, "totalVolume", None))
        if bar_volume is None:
            bar_volume = 0.0
        return Candle(
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar_volume),
            timestamp=getattr(bar, "timestamp", None),
        )

    candles = [_normalize_bar(bar) for bar in candles]
    raw_session = session_label or session_phase or _get_value(row, "session_label")
    if not str(raw_session or "").strip():
        quality_flags.append("missing_canonical_session")
    session = normalize_session_label(str(raw_session or ""))
    volume_min, _rvol_min = _session_thresholds(session)
    premarket_candles = [candle for candle in candles if _is_premarket_candle(candle)]
    if not premarket_candles and session == "PRE":
        premarket_candles = candles
    if not premarket_candles:
        premarket_candles = candles
    hod = max((_safe_float(candle.high) for candle in candles), default=None)
    lod = min((_safe_float(candle.low) for candle in candles), default=None)
    premarket_high = max((_safe_float(candle.high) for candle in premarket_candles), default=None)
    premarket_low = min((_safe_float(candle.low) for candle in premarket_candles), default=None)
    prior_close = _safe_float(_get_value(row, "prior_close") or _get_value(row, "reference_price") or _get_value(row, "prev_close") or _get_value(row, "close"))
    closes = [float(candle.close) for candle in candles]
    ema9 = _coalesce(_safe_float(_get_value(row, "ema9")), _ema(closes, 9))
    ema20 = _coalesce(_safe_float(_get_value(row, "ema20")), _ema(closes, 20))
    vwap = _coalesce(_safe_float(_get_value(row, "vwap")), _safe_float(_get_value(row, "vwap_price")), _vwap(candles))
    pct_change = _coalesce(
        _safe_float(_get_value(row, "pct_change")),
        _safe_float(_get_value(row, "pct_change_resolved")),
    )
    inferred_intraday_volume = round(
        sum(max(_safe_float(candle.volume) or 0.0, 0.0) for candle in candles),
        2,
    )
    market_volume = _coalesce(volume, inferred_intraday_volume)
    if volume is not None and volume <= 100.0 and inferred_intraday_volume > volume:
        market_volume = inferred_intraday_volume
    if market_volume is not None and market_volume <= 100.0:
        quality_flags.append("INVALID_VOLUME")
        print(f"[DATA][REJECT] symbol={symbol} reason=INVALID_VOLUME value={market_volume}")
    elif market_volume is not None and market_volume < volume_min:
        quality_flags.append("LOW_VOLUME")
        print(
            f"[DATA][REJECT] symbol={symbol} reason=LOW_VOLUME value={market_volume} "
            f"min_required={volume_min} session={session}"
        )
    reference_price = _infer_reference_price(row=row, candles=candles, session=session, prior_close=prior_close)
    if pct_change is None and last_price is not None and reference_price not in (None, 0):
        pct_change = round(((last_price - float(reference_price)) / float(reference_price)) * 100.0, 6)
    avg_volume_20d = _coalesce(
        _safe_float(_get_value(row, "avg_volume_20d")),
        _safe_float(_get_value(row, "average_daily_volume_20d")),
    )
    rvol_payload = compute_session_relative_volume_with_provenance(
        session_label=session,
        session_volume=market_volume,
        avg_volume_20d=avg_volume_20d,
        persisted_rvol=_safe_float(_get_value(row, "persisted_rvol")),
        symbol=symbol,
    )
    rvol = _coalesce(
        _safe_float(_get_value(row, "rvol")),
        _safe_float(_get_value(row, "relative_volume")),
        _safe_float(_get_value(row, "rvol_discovery")),
        rvol_payload.value,
        _rolling_rvol(total_volume=market_volume, candles=candles),
    )
    if rvol is not None:
        rvol_class = "WEAK" if rvol < 0.5 else "VALID"
        print(f"[DATA][RVOL] symbol={symbol} rvol={round(rvol, 4)} classification={rvol_class}")
        if rvol < 0.5:
            quality_flags.append("RVOL_WEAK")
    float_millions = _resolve_float_millions(symbol, row, quality_flags)
    levels = LevelSet(
        premarket_high=_coalesce(_safe_float(_get_value(row, "premarket_high")), premarket_high),
        premarket_low=_coalesce(_safe_float(_get_value(row, "premarket_low")), premarket_low),
        hod=_coalesce(_safe_float(_get_value(row, "hod")), hod),
        lod=_coalesce(_safe_float(_get_value(row, "lod")), lod),
        prior_close=prior_close,
    )
    indicators = IndicatorSet(
        ema9=ema9,
        ema20=ema20,
        ema50=_safe_float(_get_value(row, "ema50")),
        ema200=_safe_float(_get_value(row, "ema200")),
        vwap=vwap,
    )
    spread = _safe_float(_get_value(row, "spread"))
    if spread is None and bid is not None and ask is not None:
        spread = round(ask - bid, 4)
    if spread is None and (bid is None or ask is None):
        quality_flags.append("SPREAD_UNKNOWN")
    liquidity = LiquidityContext(
        spread=spread,
        float_millions=float_millions,
        rvol=rvol,
    )
    if indicators.ema9 is None or indicators.ema20 is None or indicators.vwap is None:
        quality_flags.append("indicators_incomplete")
    if levels.premarket_high is None or levels.premarket_low is None or levels.hod is None or levels.lod is None:
        quality_flags.append("levels_incomplete")
    if pct_change is None:
        quality_flags.append("pct_change_missing")
    if rvol is None:
        quality_flags.append("rvol_missing")
    session_context = SessionContext.REGULAR if session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REGULAR", "POWER_HOUR", "LATE"} else SessionContext.AFTER if session in {"AH", "AFTER"} else SessionContext.PRE
    inputs = PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=session_context,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
        news_context={
            "session_label": session,
            "session_phase": normalize_session_label(str(session_phase or session)),
            "candle_count": str(len(candles)),
            "pct_change": "" if pct_change is None else str(pct_change),
            "reference_price": "" if reference_price is None else str(reference_price),
            "bid": "" if bid is None else str(bid),
            "ask": "" if ask is None else str(ask),
            "volume": "" if market_volume is None else str(market_volume),
            "rvol_baseline": rvol_payload.baseline,
            "rvol_method": rvol_payload.method,
        },
        data_quality_flags=sorted(set(quality_flags)),
    )
    return inputs, sorted(set(quality_flags))
