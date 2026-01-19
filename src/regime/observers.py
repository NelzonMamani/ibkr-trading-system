from __future__ import annotations

from statistics import median
from typing import Iterable, List, Sequence

from src.models.data_models import ScannerCandidate
from src.regime.contracts import FeatureVector, RegimeDataQualityFlag


_SPREAD_BPS_THIN = 50.0
_ORDERBOOK_SPREAD_PCT = 0.005


def _safe_median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _sorted_candidates(candidates: Iterable[ScannerCandidate]) -> List[ScannerCandidate]:
    return sorted(candidates, key=lambda candidate: candidate.symbol or "")


def observe_features(
    *,
    candidates: Sequence[ScannerCandidate],
    session: str,
    feature_set: str = "BASIC",
) -> tuple[FeatureVector, List[RegimeDataQualityFlag]]:
    ordered = _sorted_candidates(candidates or [])
    universe_count = len(ordered)
    missing_price = 0
    missing_volume = 0
    spreads_bps: List[float] = []
    rvols: List[float] = []
    gaps: List[float] = []
    momentum_moves: List[float] = []
    extension_moves: List[float] = []
    orderbook_good = 0
    orderbook_total = 0
    flags: List[RegimeDataQualityFlag] = []

    for candidate in ordered:
        price = candidate.price
        if price is None or price <= 0:
            missing_price += 1
        spread = candidate.spread
        if spread is None:
            pass
        elif price and price > 0:
            spreads_bps.append((spread / price) * 10000.0)
        else:
            spreads_bps.append(abs(spread) * 10000.0)

        volume = candidate.volume
        if volume is None:
            missing_volume += 1

        if candidate.rvol is not None:
            rvols.append(candidate.rvol)
        if candidate.gap_percent is not None:
            gaps.append(candidate.gap_percent)
        if candidate.momentum_move_pct is not None:
            momentum_moves.append(candidate.momentum_move_pct)
        if candidate.extension_pct is not None:
            extension_moves.append(candidate.extension_pct)

        if candidate.bid is not None and candidate.ask is not None and price:
            orderbook_total += 1
            spread_pct = abs(candidate.ask - candidate.bid) / max(price, 0.0001)
            if spread_pct <= _ORDERBOOK_SPREAD_PCT:
                orderbook_good += 1

    pct_missing_prices = 1.0 if universe_count == 0 else missing_price / universe_count
    pct_missing_volume = 1.0 if universe_count == 0 else missing_volume / universe_count

    median_spread_bps = _safe_median(spreads_bps)
    median_rvol = _safe_median(rvols)
    median_gap_pct = _safe_median(gaps)
    top1_momentum_move_pct = max(momentum_moves) if momentum_moves else None

    if median_spread_bps is None:
        flags.append(RegimeDataQualityFlag.MISSING_SPREAD)
    if median_rvol is None:
        flags.append(RegimeDataQualityFlag.MISSING_RVOL)
    if median_gap_pct is None:
        flags.append(RegimeDataQualityFlag.MISSING_GAP)
    if top1_momentum_move_pct is None:
        flags.append(RegimeDataQualityFlag.MISSING_MOMENTUM)

    if pct_missing_prices > 0:
        flags.append(RegimeDataQualityFlag.MISSING_PRICE)
    if pct_missing_volume > 0:
        flags.append(RegimeDataQualityFlag.MISSING_VOLUME)

    news_density_proxy = 0.0
    flags.append(RegimeDataQualityFlag.MISSING_NEWS)

    liquidity_thin_flag = False
    if universe_count == 0 or pct_missing_volume > 0.5:
        liquidity_thin_flag = True
    if median_spread_bps is None or median_spread_bps > _SPREAD_BPS_THIN:
        liquidity_thin_flag = True
    if liquidity_thin_flag:
        flags.append(RegimeDataQualityFlag.THIN_LIQUIDITY)

    return_volatility_proxy = None
    range_expansion_proxy = None
    orderbook_quality_proxy = None

    if feature_set.upper() == "EXTENDED":
        if len(momentum_moves) >= 2:
            mean = sum(momentum_moves) / len(momentum_moves)
            variance = sum((value - mean) ** 2 for value in momentum_moves) / len(
                momentum_moves
            )
            return_volatility_proxy = variance ** 0.5
        if extension_moves:
            range_expansion_proxy = _safe_median(extension_moves)
        elif momentum_moves:
            range_expansion_proxy = _safe_median(momentum_moves)
        if orderbook_total > 0:
            orderbook_quality_proxy = orderbook_good / orderbook_total
        else:
            flags.append(RegimeDataQualityFlag.MISSING_ORDERBOOK)

    features = FeatureVector(
        session=session,
        universe_count=universe_count,
        median_spread_bps=_round(median_spread_bps),
        pct_missing_prices=_round(pct_missing_prices) or 0.0,
        pct_missing_volume=_round(pct_missing_volume) or 0.0,
        median_rvol=_round(median_rvol),
        median_gap_pct=_round(median_gap_pct),
        top1_momentum_move_pct=_round(top1_momentum_move_pct),
        news_density_proxy=_round(news_density_proxy) or 0.0,
        liquidity_thin_flag=liquidity_thin_flag,
        feature_set=feature_set.upper(),
        return_volatility_proxy=_round(return_volatility_proxy),
        range_expansion_proxy=_round(range_expansion_proxy),
        orderbook_quality_proxy=_round(orderbook_quality_proxy),
    )

    return features, _dedupe_flags(flags)


def _dedupe_flags(flags: Iterable[RegimeDataQualityFlag]) -> List[RegimeDataQualityFlag]:
    seen = set()
    deduped: List[RegimeDataQualityFlag] = []
    for flag in flags:
        if flag in seen:
            continue
        seen.add(flag)
        deduped.append(flag)
    return deduped
