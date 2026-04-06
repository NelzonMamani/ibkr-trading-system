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


def resolve_execution_price(snapshot: Any) -> float | None:
    last = _as_float(getattr(snapshot, "last", None) if not isinstance(snapshot, Mapping) else snapshot.get("last"))
    if last is not None:
        return last
    mid = _mid_from_bid_ask(snapshot)
    if mid is not None:
        return mid
    bid = _as_float(getattr(snapshot, "bid", None) if not isinstance(snapshot, Mapping) else snapshot.get("bid"))
    if bid is not None:
        return bid
    ask = _as_float(getattr(snapshot, "ask", None) if not isinstance(snapshot, Mapping) else snapshot.get("ask"))
    if ask is not None:
        return ask
    return None


def _resolve_from_ibkr_snapshot(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    cached_snapshot = context.get("ibkr_snapshot_by_symbol")
    if isinstance(cached_snapshot, Mapping):
        row = cached_snapshot.get(symbol)
        cached = resolve_execution_price(row)
        if cached is not None:
            return ResolvedPrice(cached, "IBKR_SNAPSHOT")
    else:
        cached = _extract_symbol_price(cached_snapshot, symbol)
        if cached is not None:
            return ResolvedPrice(cached, "IBKR_SNAPSHOT")

    ticker = context.get("ibkr_snapshot_ticker")
    ticker_symbol = str(getattr(ticker, "symbol", "") or "").upper()
    if ticker is not None and ticker_symbol == symbol:
        resolved = resolve_execution_price(ticker)
        if resolved is not None:
            return ResolvedPrice(resolved, "IBKR_SNAPSHOT")

    return None


def _resolve_from_ibkr_stream(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    stream = context.get("ibkr_stream_by_symbol")
    if not isinstance(stream, Mapping):
        return None
    row = stream.get(symbol)
    if row is None:
        return None
    resolved = resolve_execution_price(row)
    if resolved is not None:
        return ResolvedPrice(resolved, "IBKR_STREAM")
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
            print(f"[PRICE][RESOLVED] symbol={normalized} source=IBKR price={resolved.price} mode=PARTIAL_OK")
            return resolved.price, resolved.source

    print(f"[PRICE][WAIT] symbol={normalized} reason=NO_IBKR_DATA")
    raise PriceResolutionError(normalized, "NO_IBKR_PRICE_AVAILABLE")
