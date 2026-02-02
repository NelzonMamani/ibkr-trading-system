"""Adapters for wiring Mean Reversion policy into system contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import uuid4

from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import TradeIntent as ModelTradeIntent
from src.regime.contracts import RegimeLabel, RegimeSnapshot
from src.scanner.result_models import CandidateMetrics
from src.scanner.session_pct_change import normalize_session_label
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MarketRegimeFacts,
    PolicyDecision,
    ScannerFacts,
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
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce(*values: Optional[float]) -> Optional[float]:
    for value in values:
        if value is None:
            continue
        return value
    return None


def _snapshot_spread(snapshot: MarketSnapshot | None) -> Optional[float]:
    if snapshot is None or snapshot.bid is None or snapshot.ask is None:
        return None
    return snapshot.ask - snapshot.bid


def _parse_timestamp(timestamp_utc: str | None) -> Optional[datetime]:
    if not timestamp_utc:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_utc)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
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
    last = _coalesce(
        _safe_float(getattr(snapshot, "last", None)),
        _safe_float(getattr(candidate, "last_price", None)),
        _safe_float(getattr(candidate, "last", None)),
    )
    bid = _coalesce(
        _safe_float(getattr(snapshot, "bid", None)),
        _safe_float(getattr(candidate, "bid", None)),
    )
    ask = _coalesce(
        _safe_float(getattr(snapshot, "ask", None)),
        _safe_float(getattr(candidate, "ask", None)),
    )
    spread = _snapshot_spread(snapshot)
    if spread is None and bid is not None and ask is not None:
        spread = ask - bid
    spread = _coalesce(spread, _safe_float(getattr(candidate, "spread", None)))
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
    normalized_session = normalize_session_label(session_label or getattr(candidate, "session_label", "") or "")
    is_rth = normalized_session == "RTH"
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
        volume_deceleration_flag=bool(
            getattr(candidate, "volume_deceleration_flag", False)
        ),
        failed_breakout_up_flag=bool(getattr(candidate, "failed_breakout_up_flag", False)),
        failed_breakout_down_flag=bool(getattr(candidate, "failed_breakout_down_flag", False)),
        rejection_wick_up_flag=bool(getattr(candidate, "rejection_wick_up_flag", False)),
        rejection_wick_down_flag=bool(getattr(candidate, "rejection_wick_down_flag", False)),
        has_fresh_news=bool(getattr(candidate, "catalyst_present", False)),
        halt_flag=bool(getattr(candidate, "halted", False)),
        ssr_flag=bool(getattr(candidate, "ssr", False)),
        is_rth=is_rth,
        minutes_since_open=minutes_since_open,
        vwap_slope=_safe_float(getattr(candidate, "vwap_slope", None)),
    )


def build_market_regime_facts(
    regime_snapshot: RegimeSnapshot | None,
) -> MarketRegimeFacts:
    if regime_snapshot is None:
        return MarketRegimeFacts()
    label = regime_snapshot.label
    trending_flag = label == RegimeLabel.TRENDING
    return MarketRegimeFacts(
        spy_trending_up=trending_flag,
        spy_trending_down=trending_flag,
        qqq_trending_up=trending_flag,
        qqq_trending_down=trending_flag,
        high_volatility_day=label == RegimeLabel.HIGH_VOL_RISK_OFF,
        major_macro_event_window=label == RegimeLabel.NEWS_DRIVEN,
    )


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
