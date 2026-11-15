"""Adapters for wiring Mean Reversion policy into system contracts."""

from __future__ import annotations

from datetime import datetime
import math
import os
from typing import Iterable, Optional
from uuid import uuid4

from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import TradeIntent as ModelTradeIntent
from src.regime.contracts import RegimeSnapshot
from src.scanner.result_models import CandidateMetrics
from src.market_data.session_pct_change import normalize_session_label, resolve_market_session_context
from src.config.config_resolver import get_config
from src.domain.quote_freshness import evidence_rejection, quote_evidence
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MarketRegimeFacts,
    PolicyDecision,
    ScannerFacts,
    quote_spread_consistent,
)
from src.strategies.strategy_contracts import (
    Direction,
    StrategyDecision,
    TradeIntent as StrategyTradeIntent,
    DecisionType,
    TimeInForcePolicy,
)
from src.utils.time_utils import to_ny_time


def _safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _coalesce(*values: Optional[float]) -> Optional[float]:
    for value in values:
        if value is None:
            continue
        return value
    return None


def _parse_timestamp(timestamp_utc: str | None) -> Optional[datetime]:
    if not timestamp_utc:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_utc)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _minutes_since_open(timestamp_utc: str | None) -> Optional[int]:
    parsed = _parse_timestamp(timestamp_utc)
    if parsed is None:
        return None
    ny_time = to_ny_time(parsed)
    session_open = ny_time.replace(
        hour=9,
        minute=30,
        second=0,
        microsecond=0,
    )
    if ny_time < session_open:
        return None
    delta = ny_time - session_open
    return int(delta.total_seconds() // 60)


def build_scanner_facts(
    candidate: CandidateMetrics,
    snapshot: MarketSnapshot | None,
    *,
    timestamp_utc: str | None = None,
    session_label: str | None = None,
) -> ScannerFacts:
    errors: list[str] = []
    # A supplied snapshot owns its entire quote. Never hide a bad/missing field
    # by falling through to a different acquisition's candidate price.
    quote = snapshot if snapshot is not None else candidate
    last = _safe_float(getattr(quote, "last" if snapshot is not None else "last_price", None))
    bid = _safe_float(getattr(quote, "bid", None))
    ask = _safe_float(getattr(quote, "ask", None))
    spread = ask - bid if bid is not None and ask is not None else None
    if snapshot is not None:
        if snapshot.symbol != getattr(candidate, "symbol", None):
            errors.append("FOREIGN_QUOTE_SYMBOL")
        if (getattr(candidate, "con_id", None) is not None and snapshot.con_id is not None
                and candidate.con_id != snapshot.con_id):
            errors.append("FOREIGN_QUOTE_SECURITY")
        evidence = quote_evidence(snapshot.market_timestamp_utc, snapshot.timestamp_source,
                                  snapshot.data_quality_flags)
    else:
        evidence = getattr(candidate, "quote_evidence", None)
    assessed = _parse_timestamp(timestamp_utc)
    quote_time_valid = assessed is not None and evidence_rejection(evidence, now=assessed) is None
    retained_evidence = getattr(candidate, "quote_evidence", None)
    if snapshot is not None and retained_evidence is not None:
        quote_time_valid = quote_time_valid and evidence_rejection(retained_evidence, now=assessed) is None
    if snapshot is None:
        supplied_spread = getattr(candidate, "spread", None)
        if supplied_spread is not None and (
                _safe_float(supplied_spread) is None or supplied_spread <= 0 or
                (spread is not None and not quote_spread_consistent(bid, ask, supplied_spread))):
            errors.append("INVALID_OR_CONFLICTING_SPREAD")
    # Missing optional markers are absence of support, never positive evidence.
    def marker(name):
        return getattr(candidate, name, None) is True

    def status(name):
        value = getattr(candidate, name, None)
        if value is not None and type(value) is not bool:
            errors.append("INVALID_" + name.upper())
            return None
        return value

    for name in ("vwap", "ema9", "ema20", "atr", "hod", "lod", "vwap_slope"):
        value = getattr(candidate, name, None)
        if value is not None and _safe_float(value) is None:
            errors.append("INVALID_" + name.upper())
    vwap = _safe_float(getattr(candidate, "vwap", None))
    ema9 = _safe_float(getattr(candidate, "ema9", None))
    ema20 = _safe_float(getattr(candidate, "ema20", None))
    atr = _safe_float(getattr(candidate, "atr", None))
    hod = _safe_float(getattr(candidate, "hod", None))
    lod = _safe_float(getattr(candidate, "lod", None))
    rvol = _coalesce(
        _safe_float(getattr(candidate, "rvol", None)),
        _safe_float(getattr(candidate, "relative_volume", None)),
    )
    raw_session = session_label if session_label is not None else getattr(candidate, "session_label", None)
    raw_session = raw_session if isinstance(raw_session, str) else ""
    normalized_session = normalize_session_label(raw_session or "")
    # Label aliases constrain the actual time owner; they cannot enroll an
    # override, weekend, holiday or a different actual phase.
    override = bool(get_config("SESSION_PHASE_OVERRIDE")) or any(
        os.getenv(key, "").strip() for key in ("FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE")
    )
    actual = resolve_market_session_context(assessed) if assessed is not None else None
    coarse_rth = str(raw_session or "").upper() in {"RTH", "REG", "REGULAR"}
    is_rth = bool(not override and actual is not None and actual.coarse == "RTH" and
                  (coarse_rth or normalized_session == actual.phase))
    minutes_since_open = _minutes_since_open(timestamp_utc) if is_rth else None
    last_value = last or 0.0
    dist_from_vwap = (last_value - vwap) if vwap is not None and last is not None else None
    dist_from_ema9 = (last_value - ema9) if ema9 is not None and last is not None else None
    dist_from_ema20 = (last_value - ema20) if ema20 is not None and last is not None else None
    return ScannerFacts(
        symbol=getattr(candidate, "symbol", "") or "",
        last=last_value,
        vwap=vwap,
        ema9=ema9,
        ema20=ema20,
        atr=atr,
        hod=hod,
        lod=lod,
        spread=spread,
        dist_from_vwap=dist_from_vwap,
        dist_from_ema9=dist_from_ema9,
        dist_from_ema20=dist_from_ema20,
        rvol=rvol,
        impulse_strength=_safe_float(getattr(candidate, "impulse_strength", None)),
        volume_deceleration_flag=marker("volume_deceleration_flag"),
        failed_breakout_up_flag=marker("failed_breakout_up_flag"),
        failed_breakout_down_flag=marker("failed_breakout_down_flag"),
        rejection_wick_up_flag=marker("rejection_wick_up_flag"),
        rejection_wick_down_flag=marker("rejection_wick_down_flag"),
        has_fresh_news=status("catalyst_present"),
        halt_flag=status("halted"),
        ssr_flag=status("ssr"),
        bid=bid,
        ask=ask,
        data_quality_ok=(getattr(candidate, "data_quality_ok", None) is True and
                         not getattr(candidate, "data_quality_flags", ()) and
                         not getattr(candidate, "data_integrity_flags", ()) and
                         not getattr(snapshot, "data_quality_flags", ())),
        quote_time_valid=quote_time_valid,
        source_fact_errors=tuple(errors),
        is_rth=is_rth,
        minutes_since_open=minutes_since_open,
        vwap_slope=_safe_float(getattr(candidate, "vwap_slope", None)),
    )


def build_market_regime_facts(
    regime_snapshot: RegimeSnapshot | None,
) -> MarketRegimeFacts:
    # A single aggregate regime label cannot prove four index directions or
    # absence of an event window. The active runner has no such fact producer.
    # Preserve unknown rather than minting safe-looking False values.
    return MarketRegimeFacts()


def _confidence_from_decision(decision: PolicyDecision) -> float:
    rr = decision.diagnostics.get("rr")
    if rr is None:
        return 0.5 if decision.allowed else 0.0
    try:
        score = float(rr) / 3.0
    except (TypeError, ValueError):
        score = 0.5
    return max(0.0, min(score, 1.0))


def policy_decision_to_model_intent(
    decision: PolicyDecision,
    *,
    facts: ScannerFacts,
    strategy_name: str,
    trader_type: str,
    data_quality_flags: Iterable[str] | None = None,
) -> ModelTradeIntent | None:
    if not decision.allowed or decision.intent is None:
        return None
    intent = decision.intent
    rationale = "; ".join(
        segment
        for segment in [decision.reason, intent.thesis, intent.notes]
        if segment
    )
    return ModelTradeIntent(
        symbol=intent.symbol,
        direction=intent.side.value,
        strategy_name=strategy_name,
        confidence=_confidence_from_decision(decision),
        rationale=rationale,
        trader_type=trader_type,
        stop_loss_price=intent.stop_price,
        take_profit_price=intent.target_price,
        pattern_name=decision.setup,
        invalidation_level=intent.stop_price,
        rvol=facts.rvol,
        data_quality_flags=list(data_quality_flags or []),
    )


def policy_decision_to_strategy_decision(
    decision: PolicyDecision,
    *,
    strategy_id: str,
) -> StrategyDecision:
    intents: list[StrategyTradeIntent] = []
    decision_type = DecisionType.NO_ACTION
    if decision.allowed and decision.intent is not None:
        intent = decision.intent
        direction = Direction.LONG if intent.side.value == "LONG" else Direction.SHORT
        tif = TimeInForcePolicy.DAY
        try:
            tif = TimeInForcePolicy[intent.tif.value]
        except KeyError:
            tif = TimeInForcePolicy.DAY
        intents.append(
            StrategyTradeIntent(
                intent_id=str(uuid4()),
                symbol=intent.symbol,
                direction=direction,
                entry_model=intent.entry_type.value,
                stop_model="MEAN_REVERSION_STOP",
                target_model="MEAN_REVERSION_TARGET",
                time_in_force_policy=tif,
                invalidations=[
                    f"stop_price={intent.stop_price:.4f}",
                    f"target_price={intent.target_price:.4f}",
                ],
                rationale_text=decision.reason or intent.thesis,
                risk_flags=[],
            )
        )
        decision_type = DecisionType.EMIT_INTENT
    return StrategyDecision(
        symbol=decision.symbol,
        strategy_id=strategy_id,
        decision_type=decision_type,
        confidence=_confidence_from_decision(decision),
        rationale_text=decision.reason,
        risk_flags=[],
        intents=intents,
    )
