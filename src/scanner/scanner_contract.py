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

    def require_non_empty(label: str, value: Optional[str]) -> None:
        if value is None or not str(value).strip():
            errors.append(f"{label} must be non-empty")

    require_non_empty("strategy_name", request.strategy_name)
    require_non_empty("policy_name", request.policy_name)
    require_non_empty("ranking_intent", request.ranking_intent)

    if request.requested_top_n <= 0:
        errors.append("requested_top_n must be > 0")

    if request.above_price is not None and request.above_price < 0:
        errors.append("above_price must be >= 0")
    if request.below_price is not None and request.below_price < 0:
        errors.append("below_price must be >= 0")
    if (
        request.above_price is not None
        and request.below_price is not None
        and request.above_price > request.below_price
    ):
        errors.append("above_price must be <= below_price")

    if request.universe_source == UniverseSource.IBKR_TOP_GAINERS:
        require_non_empty("ibkr_scan_code", request.ibkr_scan_code)
        require_non_empty("instrument", request.instrument)
        require_non_empty("location_code", request.location_code)

    if request.optional_symbols_override is not None:
        symbols = [
            symbol
            for symbol in request.optional_symbols_override
            if isinstance(symbol, str) and symbol.strip()
        ]
        if not symbols:
            errors.append("optional_symbols_override must include at least one symbol")

    if request.exchanges is not None:
        exchanges = [
            exchange
            for exchange in request.exchanges
            if isinstance(exchange, str) and exchange.strip()
        ]
        if not exchanges:
            errors.append("exchanges must include at least one exchange")

    return errors
