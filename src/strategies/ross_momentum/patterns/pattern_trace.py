from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from src.domain.market_snapshot import MarketSnapshot
from src.scanner.result_models import CandidateMetrics
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.strategy_contracts import SessionContext


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
    bid = _safe_float(getattr(snapshot, "bid", None))
    ask = _safe_float(getattr(snapshot, "ask", None))
    last = _safe_float(getattr(snapshot, "last", None))
    row_last = _safe_float(_get_value(row, "last_price") or _get_value(row, "price"))
    volume = _safe_float(getattr(snapshot, "volume", None) or _get_value(row, "volume"))
    spread = _safe_float(_get_value(row, "spread"))
    if spread is None and bid is not None and ask is not None:
        spread = round(ask - bid, 4)
    levels_present = [name for name in ("premarket_high", "premarket_low", "hod", "lod", "prior_close") if _get_value(row, name) is not None]
    indicators_present = [name for name in ("ema9", "ema20", "ema50", "ema200", "vwap") if _get_value(row, name) is not None]
    missing_fields = []
    for name, value in {
        "last_price": last if last is not None else row_last,
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "rvol": _get_value(row, "rvol"),
        "float_millions": _get_value(row, "float_millions"),
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
        pct_change=_safe_float(_get_value(row, "pct_change") or _get_value(row, "pct_change_resolved")),
        rvol=_safe_float(_get_value(row, "rvol") or _get_value(row, "relative_volume")),
        float_millions=_safe_float(_get_value(row, "float_millions")),
        has_levels=bool(levels_present),
        levels_present=levels_present,
        has_indicators=bool(indicators_present),
        indicators_present=indicators_present,
        session_context=getattr(inputs.session_context, "value", None) if inputs else session_label,
        timeframe=inputs.timeframe if inputs else None,
        quality_flags=list(quality_flags or []) + list(getattr(inputs, "data_quality_flags", []) if inputs else []),
        missing_fields=sorted(set(missing_fields)),
    )


def build_runtime_pattern_inputs(*, symbol: str, row: Any, snapshot: MarketSnapshot | None, session_label: str | None, session_phase: str | None) -> tuple[PatternInputs | None, list[str]]:
    quality_flags: list[str] = list(_get_value(row, "data_quality_flags") or [])
    last = _safe_float(getattr(snapshot, "last", None))
    bid = _safe_float(getattr(snapshot, "bid", None))
    ask = _safe_float(getattr(snapshot, "ask", None))
    volume = _safe_float(getattr(snapshot, "volume", None) or _get_value(row, "volume"))
    row_last = _safe_float(_get_value(row, "last_price") or _get_value(row, "price"))
    last_price = last if last is not None else row_last
    if last_price is None:
        quality_flags.append("missing_last_price")
    if bid is None:
        quality_flags.append("missing_bid")
    if ask is None:
        quality_flags.append("missing_ask")
    if volume is None:
        quality_flags.append("missing_volume")
    candles: list[Candle] = []
    if last_price is not None:
        candle_volume = int(volume) if volume is not None else 0
        candles.append(Candle(open=last_price, high=last_price, low=last_price, close=last_price, volume=candle_volume))
    levels = LevelSet(
        premarket_high=_safe_float(_get_value(row, "premarket_high")),
        premarket_low=_safe_float(_get_value(row, "premarket_low")),
        hod=_safe_float(_get_value(row, "hod")),
        lod=_safe_float(_get_value(row, "lod")),
        prior_close=_safe_float(_get_value(row, "prior_close") or _get_value(row, "reference_price") or _get_value(row, "prev_close")),
    )
    indicators = IndicatorSet(
        ema9=_safe_float(_get_value(row, "ema9")),
        ema20=_safe_float(_get_value(row, "ema20")),
        ema50=_safe_float(_get_value(row, "ema50")),
        ema200=_safe_float(_get_value(row, "ema200")),
        vwap=_safe_float(_get_value(row, "vwap")),
    )
    spread = _safe_float(_get_value(row, "spread"))
    if spread is None and bid is not None and ask is not None:
        spread = round(ask - bid, 4)
    liquidity = LiquidityContext(
        spread=spread or 0.0,
        float_millions=_safe_float(_get_value(row, "float_millions")),
        rvol=_safe_float(_get_value(row, "rvol") or _get_value(row, "relative_volume")),
    )
    session = str(session_label or session_phase or _get_value(row, "session_label") or "PRE").upper()
    session_context = SessionContext.REGULAR if session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REGULAR"} else SessionContext.AFTER if session in {"AH", "AFTER"} else SessionContext.PRE
    inputs = PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=session_context,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
        news_context={"session_label": session, "session_phase": str(session_phase or session)},
        data_quality_flags=sorted(set(quality_flags)),
    )
    return inputs, sorted(set(quality_flags))
