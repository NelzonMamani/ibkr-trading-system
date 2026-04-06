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


def _extract_snapshot_row(mapping: Mapping[str, Any] | None, symbol: str) -> Mapping[str, Any] | None:
    if not isinstance(mapping, Mapping):
        return None
    row = mapping.get(symbol)
    if not isinstance(row, Mapping):
        return None
    return row


def _mid_from_bid_ask(container: Any) -> float | None:
    bid = _as_float(getattr(container, "bid", None) if not isinstance(container, Mapping) else container.get("bid"))
    ask = _as_float(getattr(container, "ask", None) if not isinstance(container, Mapping) else container.get("ask"))
    if bid is None or ask is None:
        return None
    return round((bid + ask) / 2.0, 4)


def _resolve_from_ibkr_snapshot(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    cached_row = _extract_snapshot_row(context.get("ibkr_snapshot_by_symbol"), symbol)
    if cached_row is not None:
        last = _as_float(cached_row.get("last") or cached_row.get("last_price") or cached_row.get("price"))
        if last is not None:
            return ResolvedPrice(last, "IBKR_SNAPSHOT")
        mid = _mid_from_bid_ask(cached_row)
        if mid is not None:
            return ResolvedPrice(mid, "IBKR_SNAPSHOT_MID")

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


def _resolve_from_scanner(symbol: str, context: Mapping[str, Any]) -> ResolvedPrice | None:
    scanner_payload = context.get("scanner_payload")
    if not isinstance(scanner_payload, Mapping):
        return None

    for key in ("focus_m", "watchlist_k", "candidates"):
        rows = scanner_payload.get(key) or []
        for row in rows:
            row_symbol = str(getattr(row, "symbol", None) if not isinstance(row, Mapping) else row.get("symbol") or "").upper()
            if row_symbol != symbol:
                continue
            value = _as_float(getattr(row, "last_price", None) if not isinstance(row, Mapping) else row.get("last_price"))
            if value is not None:
                return ResolvedPrice(value, "SCANNER_LAST_PRICE")

    return _resolve_from_premarket(symbol, context, source="PREMARKET_PREP")


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

    mode = str(context.get("run_mode") or "").strip().upper()

    if mode in {"PAPER", "LIVE"}:
        resolved = _resolve_from_ibkr_snapshot(normalized, context)
        if resolved is not None:
            print(f"[PRICE][RESOLVE] symbol={normalized} source={resolved.source} price={resolved.price}")
            return resolved.price, resolved.source
        print(f"[PRICE][FAIL] symbol={normalized} reason=NO_VALID_SOURCE mode={mode}")
        raise PriceResolutionError(normalized, "NO_VALID_PRICE_SOURCE")

    for resolver in (
        _resolve_from_ibkr_snapshot,
        _resolve_from_ibkr_stream,
        _resolve_from_scanner,
        _resolve_from_premarket,
    ):
        resolved = resolver(normalized, context)
        if resolved is not None:
            print(f"[PRICE][RESOLVE] symbol={normalized} source={resolved.source} price={resolved.price}")
            return resolved.price, resolved.source

    print(f"[PRICE][FAIL] symbol={normalized} reason=NO_VALID_SOURCE")
    raise PriceResolutionError(normalized, "NO_VALID_PRICE_SOURCE")
