from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.preparation.level_computation import (
    StructureLevels,
    compute_gap_pct,
    compute_structure_levels,
    compute_time_normalized_rvol,
)


@dataclass
class SymbolContext:
    symbol: str
    session_label: str
    last_price: float | None
    prior_close: float | None
    session_open_price: float | None
    pct_change: float | None
    rvol: float | None
    scanner_rvol: float | None
    time_normalized_rvol: float | None
    volume: float | None
    dollar_volume: float | None
    float_millions: float | None
    news_catalyst: str | None
    premarket_high: float | None
    premarket_low: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    multi_day_high: float | None
    multi_day_low: float | None
    vwap: float | None
    ema9: float | None
    ema20: float | None
    whole_half_levels: list[float]
    hod: float | None
    lod: float | None
    impulse_high: float | None
    impulse_low: float | None
    consolidation_range: tuple[float, float] | None
    bid: float | None
    ask: float | None
    spread_pct: float | None
    halted: bool
    ssr: bool
    in_play: bool
    tradable: bool
    gate_checks: dict[str, bool] = field(default_factory=dict)
    gap_pct: float | None = None
    catalyst_quality: float = 0.0
    liquidity_penalty: float = 0.0
    focus_rank_score: float = 0.0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_liquidity_penalty(spread_pct: float | None, halted: bool, bid: float | None, ask: float | None) -> float:
    penalty = 0.0
    if spread_pct is not None:
        penalty += min(max(spread_pct * 100.0, 0.0), 15.0)
    if halted:
        penalty += 25.0
    if bid is None or ask is None:
        penalty += 10.0
    return round(penalty, 4)


def _float_inverse(float_millions: float | None) -> float:
    if float_millions is None or float_millions <= 0:
        return 0.0
    return min(1.0 / float_millions, 1.0)


def _catalyst_quality(news_context: dict[str, Any]) -> float:
    if not news_context:
        return 0.0
    if news_context.get("catalyst_type"):
        return 1.0
    if news_context.get("news_present"):
        return 0.5
    return 0.0


def rank_symbol_context(context: SymbolContext) -> float:
    pct = context.pct_change or 0.0
    rvol = context.rvol or 0.0
    float_inverse = _float_inverse(context.float_millions)
    score = (
        (pct * 0.45)
        + (rvol * 8.0 * 0.30)
        + (float_inverse * 100.0 * 0.15)
        + (context.catalyst_quality * 100.0 * 0.10)
        - context.liquidity_penalty
    )
    return round(score, 4)


def build_symbol_context(
    symbol: str,
    *,
    session_label: str = "",
    base_context: dict[str, Any] | None = None,
    news_context: dict[str, Any] | None = None,
    history_closes: list[float] | None = None,
) -> SymbolContext:
    base_context = base_context or {}
    news_context = news_context or {}

    last_price = _safe_float(base_context.get("last_price"))
    prior_close = _safe_float(base_context.get("prev_close"))
    session_open_price = _safe_float(base_context.get("rth_open_price"))

    scanner_rvol = _safe_float(base_context.get("scanner_rvol"))
    time_norm_rvol = compute_time_normalized_rvol(
        scanner_rvol=scanner_rvol,
        session_progress=None,
    )
    resolved_rvol = _safe_float(base_context.get("rvol"))
    if resolved_rvol is None:
        resolved_rvol = time_norm_rvol

    levels: StructureLevels = compute_structure_levels(
        quote={
            "last_price": last_price,
            "day_high": base_context.get("hod") or base_context.get("high"),
            "day_low": base_context.get("lod") or base_context.get("low"),
            "prior_close": prior_close,
            "vwap": base_context.get("vwap"),
        },
        intraday={
            "premarket_high": base_context.get("premarket_high"),
            "premarket_low": base_context.get("premarket_low"),
            "prior_day_high": base_context.get("prior_day_high"),
            "prior_day_low": base_context.get("prior_day_low"),
        },
        history_closes=history_closes,
    )

    bid = _safe_float(base_context.get("bid"))
    ask = _safe_float(base_context.get("ask"))
    spread_pct = _safe_float(base_context.get("spread_pct"))
    halted = bool(base_context.get("halted") or False)
    ssr = bool(base_context.get("ssr") or False)

    float_shares = _safe_float(base_context.get("float_shares"))
    float_millions = round(float_shares / 1_000_000.0, 4) if float_shares else None

    pct_change = _safe_float(base_context.get("pct_change"))

    gate_checks = {
        "has_price": last_price is not None,
        "has_volume": _safe_float(base_context.get("volume")) is not None,
        "has_liquidity": bid is not None and ask is not None,
        "not_halted": not halted,
    }
    in_play = bool((pct_change or 0.0) >= 5.0 or (resolved_rvol or 0.0) >= 2.0)
    tradable = all(gate_checks.values())

    catalyst_quality = _catalyst_quality(news_context)
    liquidity_penalty = _compute_liquidity_penalty(spread_pct, halted, bid, ask)

    context = SymbolContext(
        symbol=symbol,
        session_label=session_label,
        last_price=last_price,
        prior_close=prior_close,
        session_open_price=session_open_price,
        pct_change=pct_change,
        rvol=resolved_rvol,
        scanner_rvol=scanner_rvol,
        time_normalized_rvol=time_norm_rvol,
        volume=_safe_float(base_context.get("volume")),
        dollar_volume=_safe_float(base_context.get("dollar_volume")),
        float_millions=float_millions,
        news_catalyst=news_context.get("catalyst_type"),
        premarket_high=levels.premarket_high,
        premarket_low=levels.premarket_low,
        prior_day_high=levels.prior_day_high,
        prior_day_low=levels.prior_day_low,
        multi_day_high=levels.multi_day_high,
        multi_day_low=levels.multi_day_low,
        vwap=levels.vwap,
        ema9=levels.ema9,
        ema20=levels.ema20,
        whole_half_levels=levels.whole_half_levels,
        hod=_safe_float(base_context.get("hod")) or _safe_float(base_context.get("high")),
        lod=_safe_float(base_context.get("lod")) or _safe_float(base_context.get("low")),
        impulse_high=_safe_float(base_context.get("impulse_high")),
        impulse_low=_safe_float(base_context.get("impulse_low")),
        consolidation_range=base_context.get("consolidation_range"),
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        halted=halted,
        ssr=ssr,
        in_play=in_play,
        tradable=tradable,
        gate_checks=gate_checks,
        gap_pct=_safe_float(base_context.get("gap_pct_resolved")) or compute_gap_pct(session_open_price, prior_close),
        catalyst_quality=catalyst_quality,
        liquidity_penalty=liquidity_penalty,
    )
    context.focus_rank_score = rank_symbol_context(context)
    return context
