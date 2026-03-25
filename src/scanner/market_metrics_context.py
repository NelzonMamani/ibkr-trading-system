from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.scanner.session_pct_change import (
    compute_phase_aware_rvol,
    compute_session_aligned_pct_change,
    compute_session_relative_volume_with_provenance,
    normalize_session_label,
)


@dataclass(frozen=True)
class MarketMetricsContext:
    symbol: str
    session_label: str
    session_phase: str
    last_price: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    spread_abs: Optional[float]
    spread_pct: Optional[float]
    current_volume: Optional[float]
    avg_volume_20d: Optional[float]
    expected_volume: Optional[float]
    last_rth_close: Optional[float]
    pct_change: Optional[float]
    rvol: Optional[float]
    gap_pct: Optional[float]
    float_shares: Optional[float]
    float_millions: Optional[float]
    price_source: str
    volume_source: str
    reference_source: str
    expected_volume_source: str
    rvol_source: str
    pct_source: str
    open_relative_pct_change: Optional[float]
    time_normalized_rvol: Optional[float]
    rvol_baseline: str
    rvol_method: str


def _to_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_market_metrics_context(
    *,
    symbol: str,
    session_label: str,
    last_price: Optional[float],
    bid: Optional[float],
    ask: Optional[float],
    spread_abs: Optional[float],
    spread_pct: Optional[float],
    current_volume: Optional[float],
    avg_volume_20d: Optional[float],
    last_rth_close: Optional[float],
    rth_open_price: Optional[float],
    rth_close_price: Optional[float],
    ibkr_change_pct: Optional[float],
    persisted_pct_change: Optional[float],
    persisted_rvol: Optional[float],
    float_shares: Optional[float],
    price_source: str = "QUOTE_LAST",
    volume_source: str = "INTRADAY_OR_QUOTE_VOLUME",
    reference_source: str = "UNRESOLVED",
) -> MarketMetricsContext:
    normalized_session = normalize_session_label(session_label)
    pct_payload = compute_session_aligned_pct_change(
        session_label=normalized_session,
        cur_last=_to_float(last_price),
        ref_close_rth=_to_float(last_rth_close),
        rth_open_price=_to_float(rth_open_price),
        rth_close_price=_to_float(rth_close_price),
        ibkr_change_pct=_to_float(ibkr_change_pct),
        persisted_pct_change=_to_float(persisted_pct_change),
    )
    # Session-normalized RVOL retained as telemetry; phase-aware RVOL is authoritative gating value.
    session_rvol_payload = compute_session_relative_volume_with_provenance(
        session_label=normalized_session,
        session_volume=_to_float(current_volume),
        avg_volume_20d=_to_float(avg_volume_20d),
        persisted_rvol=_to_float(persisted_rvol),
        symbol=symbol,
    )
    phase_payload = compute_phase_aware_rvol(
        session_label=normalized_session,
        session_volume=_to_float(current_volume),
        avg_volume_20d=_to_float(avg_volume_20d),
    )
    rvol = phase_payload.rvol_phase
    rvol_source = "PHASE_MODEL"
    expected_volume_source = f"PHASE_RATIO:{normalized_session}"
    expected_volume = phase_payload.expected_phase_volume

    if rvol is None:
        rvol = session_rvol_payload.value
        rvol_source = session_rvol_payload.method
        expected_volume = session_rvol_payload.expected_volume
        expected_volume_source = session_rvol_payload.baseline

    float_value = _to_float(float_shares)
    float_millions = round(float_value / 1_000_000.0, 4) if float_value not in {None, 0.0} else None

    return MarketMetricsContext(
        symbol=symbol,
        session_label=session_label,
        session_phase=normalized_session,
        last_price=_to_float(last_price),
        bid=_to_float(bid),
        ask=_to_float(ask),
        spread_abs=_to_float(spread_abs),
        spread_pct=_to_float(spread_pct),
        current_volume=_to_float(current_volume),
        avg_volume_20d=_to_float(avg_volume_20d),
        expected_volume=_to_float(expected_volume),
        last_rth_close=_to_float(last_rth_close),
        pct_change=pct_payload.final_pct,
        rvol=rvol,
        gap_pct=pct_payload.open_relative_pct_change if pct_payload.open_relative_pct_change is not None else pct_payload.final_pct,
        float_shares=float_value,
        float_millions=float_millions,
        price_source=price_source,
        volume_source=volume_source,
        reference_source=reference_source,
        expected_volume_source=expected_volume_source,
        rvol_source=rvol_source,
        pct_source=pct_payload.pct_source,
        open_relative_pct_change=pct_payload.open_relative_pct_change,
        time_normalized_rvol=session_rvol_payload.value,
        rvol_baseline=session_rvol_payload.baseline,
        rvol_method=session_rvol_payload.method,
    )


def log_market_metrics_context(context: MarketMetricsContext) -> None:
    print(
        "[MARKET_CONTEXT] "
        f"symbol={context.symbol} "
        f"session={context.session_label} "
        f"phase={context.session_phase} "
        f"last={context.last_price} "
        f"prev_close={context.last_rth_close} "
        f"pct_change={context.pct_change} "
        f"current_volume={context.current_volume} "
        f"avg_volume_20d={context.avg_volume_20d} "
        f"expected_volume={context.expected_volume} "
        f"rvol={context.rvol} "
        f"spread_pct={context.spread_pct} "
        f"float_millions={context.float_millions} "
        f"sources=pct:{context.pct_source}|rvol:{context.rvol_source}|ref:{context.reference_source}"
    )
