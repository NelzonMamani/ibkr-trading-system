from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.scanner.contracts import StockSelectionPolicy
from src.strategies.ross_momentum.strategy_policy import UniverseSource, UniverseSpec


@dataclass(frozen=True)
class ScannerRequest:
    strategy_name: str
    policy_name: str
    ranking_intent: str
    session_phase: Optional[str]
    universe_source: UniverseSource
    ibkr_scan_code: str
    requested_top_n: int
    above_price: Optional[float] = None
    below_price: Optional[float] = None
    optional_symbols_override: Optional[Sequence[str]] = None
    region: Optional[str] = None
    instrument: Optional[str] = None
    location_code: Optional[str] = None
    exchanges: Optional[Sequence[str]] = None


def scanner_request_from_policy(
    policy: StockSelectionPolicy,
    *,
    strategy_name: Optional[str] = None,
    session_phase: Optional[str] = None,
    optional_symbols_override: Optional[Sequence[str]] = None,
) -> ScannerRequest:
    universe: UniverseSpec = getattr(policy, "universe", UniverseSpec())
    requested_top_n = universe.top_n or policy.top_gainers_n
    exchanges = list(universe.exchanges) if universe.exchanges else None
    return ScannerRequest(
        strategy_name=strategy_name or policy.policy_name,
        policy_name=policy.policy_name,
        ranking_intent=policy.ranking_intent,
        session_phase=session_phase,
        universe_source=universe.source,
        ibkr_scan_code=universe.ibkr_scan_code,
        requested_top_n=int(requested_top_n),
        above_price=policy.price_min,
        below_price=policy.price_max,
        optional_symbols_override=optional_symbols_override,
        region=universe.region,
        instrument=universe.instrument,
        location_code=universe.location_code,
        exchanges=exchanges,
    )


def validate_scanner_request(request: ScannerRequest) -> list[str]:
    errors: list[str] = []
    if not str(request.strategy_name or "").strip():
        errors.append("strategy_name is required")
    if not str(request.policy_name or "").strip():
        errors.append("policy_name is required")
    if not str(request.ranking_intent or "").strip():
        errors.append("ranking_intent is required")
    if request.requested_top_n <= 0:
        errors.append("requested_top_n must be positive")
    if request.universe_source == UniverseSource.IBKR_TOP_GAINERS:
        if not str(request.ibkr_scan_code or "").strip():
            errors.append("ibkr_scan_code is required for IBKR_TOP_GAINERS")
        if not str(request.instrument or "").strip():
            errors.append("instrument is required for IBKR_TOP_GAINERS")
        if not str(request.location_code or "").strip():
            errors.append("location_code is required for IBKR_TOP_GAINERS")
    if request.above_price is not None and request.below_price is not None:
        if request.above_price > request.below_price:
            errors.append("above_price must be <= below_price")
    return errors
