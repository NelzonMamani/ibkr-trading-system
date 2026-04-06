from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class PriceResolutionError(RuntimeError):
    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(f"{symbol}: {reason}")
        self.symbol = symbol
        self.reason = reason


@dataclass(frozen=True)
class ResolvedPrice:
    price: float
    source: str


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _extract_symbol_price(mapping: Mapping[str, Any] | None, symbol: str) -> float | None:
    if not isinstance(mapping, Mapping):
        return None
    row = mapping.get(symbol)
    if isinstance(row, Mapping):
        return _as_float(row.get("price") or row.get("last") or row.get("last_price"))
    return _as_float(row)


def _mid_from_bid_ask(container: Any) -> float | None:
    bid = _as_float(getattr(container, "bid", None) if not isinstance(container, Mapping) else container.get("bid"))
    ask = _as_float(getattr(container, "ask", None) if not isinstance(container, Mapping) else container.get("ask"))
    if bid is None or ask is None:
        return None
    return round((bid + ask) / 2.0, 4)


def _resolve_from_ibkr_snapshot(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    cached = _extract_symbol_price(context.get("ibkr_snapshot_by_symbol"), symbol)
    if cached is not None:
        return ResolvedPrice(cached, "IBKR_SNAPSHOT")

    ticker = context.get("ibkr_snapshot_ticker")
    ticker_symbol = str(getattr(ticker, "symbol", "") or "").upper()
    if ticker is not None and ticker_symbol == symbol:
        last = _as_float(getattr(ticker, "last", None))
        if last is not None:
            return ResolvedPrice(last, "IBKR_SNAPSHOT")
        mid = _mid_from_bid_ask(ticker)
        if mid is not None:
            return ResolvedPrice(mid, "IBKR_SNAPSHOT_MID")

    return None


def _resolve_from_ibkr_stream(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    stream = context.get("ibkr_stream_by_symbol")
    if not isinstance(stream, Mapping):
        return None
    row = stream.get(symbol)
    if row is None:
        return None
    last = _as_float(getattr(row, "last", None) if not isinstance(row, Mapping) else row.get("last"))
    if last is not None:
        return ResolvedPrice(last, "IBKR_STREAM")
    mid = _mid_from_bid_ask(row)
    if mid is not None:
        return ResolvedPrice(mid, "IBKR_STREAM_MID")
    return None


def _resolve_from_premarket(symbol: str, context: Mapping[str, Any], source: str = "PREMARKET_PREP_ARTIFACT") -> ResolvedPrice | None:
    prep = context.get("premarket_prep")
    if not isinstance(prep, Mapping):
        return None
    symbols = prep.get("symbols")
    if not isinstance(symbols, list):
        return None
    for row in symbols:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("symbol") or "").upper() != symbol:
            continue
        for field in ("last_price", "reference_price", "premarket_high"):
            value = _as_float(row.get(field))
            if value is not None:
                return ResolvedPrice(value, source)
    return None


def resolve_entry_price(symbol: str, context: Mapping[str, Any]) -> tuple[float, str]:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise PriceResolutionError(symbol, "INVALID_SYMBOL")

    for resolver in (
        _resolve_from_ibkr_snapshot,
        _resolve_from_ibkr_stream,
    ):
        resolved = resolver(normalized, context)
        if resolved is not None:
            print(f"[PRICE][RESOLVE] symbol={normalized} source={resolved.source} price={resolved.price}")
            return resolved.price, resolved.source

    print(f"[PRICE][FAIL] symbol={normalized} reason=NO_VALID_SOURCE")
    raise PriceResolutionError(normalized, "NO_VALID_PRICE_SOURCE")
